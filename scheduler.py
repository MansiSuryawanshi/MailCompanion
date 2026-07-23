"""
scheduler.py - Background Periodic Scheduler for Automated Campaign Runs
"""
import os
import json
import threading
import time
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Tuple
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from config import ConfigManager
from services.auth_service import AuthService
from services.email_service import EmailService
from services.followup_service import FollowupService
from services.gmail_provider import GmailProvider
from services.sheets_service import SheetsService
from utils.logger import log_campaign_action


class CampaignScheduler:
    """Manages APScheduler background automation for reading sheets, sending pending emails, and processing follow-ups."""

    def __init__(self):
        self.scheduler = BackgroundScheduler()
        self.config_manager = ConfigManager()
        self.job_id = "daily_email_campaign_job"
        self._is_running = False
        self.status_file = "data/scheduler_status.json"

    def run_campaign_job(self) -> None:
        """Background worker task executed on schedule."""
        log_campaign_action("SchedulerJob", status="INFO", message="Starting scheduled campaign automation run...")

        try:
            self.config_manager.reload()
            
            # Check if today matches custom schedule
            if not self.is_scheduled_date(datetime.now(), self.config_manager.settings):
                log_campaign_action("SchedulerJob", status="INFO", message="Scheduler skipped run: today is not a scheduled run day according to custom schedule settings.")
                return

            from constants import TOKEN_FILE
            active_campaign = self.config_manager.get_active_campaign()
            
            sender_email = getattr(active_campaign, "sender_email", None) or self.config_manager.settings.get("active_sender_email")
            token_path = f"credentials/token_{sender_email}.json" if sender_email else TOKEN_FILE
            
            auth_service = AuthService(token_path=token_path)
            if not auth_service.get_credentials():
                log_campaign_action("SchedulerJob", status="WARNING", error=f"Scheduler skipped run: OAuth credentials missing or invalid for {sender_email or 'default'}.")
                return
            if active_campaign.state != "Running":
                log_campaign_action("SchedulerJob", status="INFO", message=f"Scheduler skipped run: Campaign '{active_campaign.name}' state is '{active_campaign.state}'")
                return

            sp_id = active_campaign.spreadsheet_id
            if not sp_id:
                log_campaign_action("SchedulerJob", status="WARNING", error="Scheduler skipped run: No Spreadsheet ID configured.")
                return

            sheets_service = SheetsService(auth_service, sp_id)
            if not sheets_service.connect():
                log_campaign_action("SchedulerJob", status="ERROR", error="Scheduler failed: Unable to connect to Google Sheet.")
                return

            gmail_provider = GmailProvider(auth_service)
            email_service = EmailService(gmail_provider, sheets_service, self.config_manager)
            followup_service = FollowupService(gmail_provider, sheets_service, email_service, self.config_manager)

            # 1. Send Pending Initial Emails
            initial_res = email_service.execute_campaign_batch(active_campaign)
            log_campaign_action("SchedulerJob", status="INFO", message=f"Initial sends: {initial_res.get('message')}")

            # 2. Check and Send Follow-ups
            followup_res = followup_service.execute_followups_batch(active_campaign)
            log_campaign_action("SchedulerJob", status="INFO", message=f"Follow-ups: {followup_res.get('message')}")

            # Update last sync time
            active_campaign.last_sync_time = datetime.now().isoformat()
            self.config_manager.update_campaign(active_campaign)

            log_campaign_action("SchedulerJob", status="SUCCESS", message="Scheduled campaign automation run completed successfully.")

        except Exception as e:
            log_campaign_action("SchedulerJob", status="ERROR", error=str(e), message="Exception occurred during scheduled campaign run")

    def is_daemon_running(self) -> Tuple[bool, Optional[int]]:
        """Checks if the background daemon process is currently running."""
        if not os.path.exists(self.status_file):
            return False, None
        
        try:
            with open(self.status_file, "r", encoding="utf-8") as f:
                status = json.load(f)
            pid = status.get("pid")
            is_running_flag = status.get("is_running", False)
            
            if not pid or not is_running_flag:
                return False, None
            
            # Check OS process
            import subprocess
            import sys
            if sys.platform == "win32":
                try:
                    out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}"], capture_output=True, text=True, check=False)
                    if str(pid) in out.stdout:
                        return True, pid
                except Exception:
                    pass
            else:
                try:
                    os.kill(pid, 0)
                    return True, pid
                except OSError:
                    pass
                    
            return False, pid
        except Exception:
            return False, None

    def _write_inactive_status(self) -> None:
        try:
            if os.path.exists(self.status_file):
                with open(self.status_file, "r", encoding="utf-8") as f:
                    status = json.load(f)
                status["is_running"] = False
                status["next_run"] = "None"
                with open(self.status_file, "w", encoding="utf-8") as f:
                    json.dump(status, f, indent=4)
        except Exception:
            pass

    def start(self, cron_time_str: str = "10:00") -> bool:
        if os.environ.get("SCHEDULER_DAEMON") == "1":
            return self._start_local_scheduler(cron_time_str)
        else:
            return self._spawn_daemon(cron_time_str)

    def _start_local_scheduler(self, cron_time_str: str) -> bool:
        """Starts the actual APScheduler in-process (used inside the daemon)."""
        try:
            hour, minute = cron_time_str.split(":")
        except ValueError:
            hour, minute = "10", "00"

        if self.scheduler.get_job(self.job_id):
            self.scheduler.remove_job(self.job_id)

        trigger = CronTrigger(hour=int(hour), minute=int(minute))
        self.scheduler.add_job(self.run_campaign_job, trigger, id=self.job_id)

        if not self.scheduler.running:
            self.scheduler.start()

        self._is_running = True
        log_campaign_action("CampaignScheduler", status="SUCCESS", message=f"Scheduler started locally (Daily at {cron_time_str})")
        return True

    def _spawn_daemon(self, cron_time_str: str) -> bool:
        """Spawns the detached background daemon process (used inside Streamlit)."""
        # Stop any existing daemon first
        self.stop()

        import subprocess
        import sys
        import os

        # Save settings first so daemon has the correct scheduler time
        self.config_manager = ConfigManager()
        self.config_manager.settings["scheduler_time"] = cron_time_str
        self.config_manager.settings["scheduler_enabled"] = True
        self.config_manager.save_settings()

        # Spawn scheduler_daemon.py as a detached process
        creation_flags = 0
        if sys.platform == "win32":
            # DETACHED_PROCESS = 0x00000008
            # CREATE_NO_WINDOW = 0x08000000
            creation_flags = 0x00000008 | 0x08000000

        daemon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scheduler_daemon.py")
        
        env = os.environ.copy()
        env["SCHEDULER_DAEMON"] = "1"
        
        try:
            subprocess.Popen(
                [sys.executable, daemon_path],
                env=env,
                creationflags=creation_flags,
                close_fds=True
            )
            # Give a quick moment for the daemon to write its PID
            time.sleep(0.5)
            log_campaign_action("CampaignScheduler", status="SUCCESS", message=f"Background scheduler daemon spawned successfully at {cron_time_str}.")
            return True
        except Exception as e:
            log_campaign_action("CampaignScheduler", status="ERROR", error=str(e), message="Failed to spawn scheduler daemon process.")
            return False

    def stop(self) -> bool:
        if os.environ.get("SCHEDULER_DAEMON") == "1":
            # Stopping local scheduler inside the daemon
            if self.scheduler.running:
                self.scheduler.shutdown(wait=False)
                self.scheduler = BackgroundScheduler()
            self._is_running = False
            log_campaign_action("CampaignScheduler", status="INFO", message="Scheduler stopped locally")
            return True
        else:
            # Stopping daemon process from Streamlit
            running, pid = self.is_daemon_running()
            if running and pid:
                import subprocess
                import sys
                if sys.platform == "win32":
                    try:
                        subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True, check=False)
                    except Exception:
                        pass
                else:
                    try:
                        os.kill(pid, 9)
                    except OSError:
                        pass
            
            # Update status file to show stopped
            self._write_inactive_status()
            log_campaign_action("CampaignScheduler", status="INFO", message="Background scheduler daemon stopped.")
            return True

    def is_scheduled_date(self, date_to_check: datetime, settings: dict) -> bool:
        """Determines if a given datetime is a scheduled run day."""
        mode = settings.get("scheduler_mode", "daily")
        if mode == "daily":
            return True
            
        elif mode == "weekdays":
            weekdays = settings.get("scheduler_weekdays", [])
            if not weekdays:
                return True
            weekday_name = date_to_check.strftime("%A")  # "Monday", "Tuesday", etc.
            return weekday_name in weekdays
            
        elif mode == "dates":
            scheduled_dates = settings.get("scheduler_dates", [])
            date_str = date_to_check.strftime("%Y-%m-%d")
            return date_str in scheduled_dates
            
        elif mode == "interval":
            try:
                gap = int(settings.get("scheduler_interval_gap", 1))
            except ValueError:
                gap = 1
            start_str = settings.get("scheduler_interval_start", "")
            if not start_str:
                return True
            try:
                start_date = datetime.strptime(start_str, "%Y-%m-%d").date()
                diff_days = (date_to_check.date() - start_date).days
                if diff_days < 0:
                    return False
                return diff_days % (gap + 1) == 0
            except Exception:
                return True
                
        return True

    def calculate_next_run(self, start_from: datetime, settings: dict) -> Optional[datetime]:
        """Calculates the true next scheduled run date and time."""
        if not settings.get("scheduler_enabled", False):
            return None
            
        sched_time_str = settings.get("scheduler_time", "10:00")
        try:
            hour, minute = map(int, sched_time_str.split(":"))
        except ValueError:
            hour, minute = 10, 0
            
        # Start checking candidate days starting today
        candidate = start_from.replace(hour=hour, minute=minute, second=0, microsecond=0)
        
        for i in range(365):
            test_date = candidate + timedelta(days=i)
            # If candidate is in the past relative to start_from, skip it
            if test_date <= start_from:
                continue
            if self.is_scheduled_date(test_date, settings):
                return test_date
                
        return None

    def get_status(self) -> Dict[str, Any]:
        """Returns status indicator dict for UI dashboard."""
        if os.environ.get("SCHEDULER_DAEMON") == "1":
            # Local status (inside daemon)
            next_run_dt = self.calculate_next_run(datetime.now(), self.config_manager.settings)
            next_run = next_run_dt.strftime("%Y-%m-%d %H:%M:%S") if next_run_dt else "None"
            return {
                "is_running": self._is_running and self.scheduler.running,
                "status": "Active" if (self._is_running and self.scheduler.running) else "Inactive",
                "color": "green" if (self._is_running and self.scheduler.running) else "gray",
                "next_run": next_run,
            }
        else:
            # Streamlit status (checks daemon status file)
            running, pid = self.is_daemon_running()
            if running:
                try:
                    with open(self.status_file, "r", encoding="utf-8") as f:
                        status = json.load(f)
                    return {
                        "is_running": True,
                        "status": "Active",
                        "color": "green",
                        "next_run": status.get("next_run", "None"),
                    }
                except Exception:
                    pass
            return {
                "is_running": False,
                "status": "Inactive",
                "color": "gray",
                "next_run": "None",
            }


# Singleton instance
global_scheduler = CampaignScheduler()
