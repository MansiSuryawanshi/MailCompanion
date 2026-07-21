"""
scheduler.py - Background Periodic Scheduler for Automated Campaign Runs
"""
import threading
import time
from datetime import datetime
from typing import Any, Dict, Optional
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

    def run_campaign_job(self) -> None:
        """Background worker task executed on schedule."""
        log_campaign_action("SchedulerJob", status="INFO", message="Starting scheduled campaign automation run...")

        try:
            auth_service = AuthService()
            if not auth_service.get_credentials():
                log_campaign_action("SchedulerJob", status="WARNING", error="Scheduler skipped run: OAuth credentials missing or invalid.")
                return

            active_campaign = self.config_manager.get_active_campaign()
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

    def start(self, cron_time_str: str = "10:00") -> bool:
        """Starts background scheduler with a daily cron trigger at given HH:MM."""
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
        log_campaign_action("CampaignScheduler", status="SUCCESS", message=f"Scheduler started (Daily at {cron_time_str})")
        return True

    def stop(self) -> bool:
        """Stops background scheduler."""
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
            self.scheduler = BackgroundScheduler()
        self._is_running = False
        log_campaign_action("CampaignScheduler", status="INFO", message="Scheduler stopped")
        return True

    def get_status(self) -> Dict[str, Any]:
        """Returns status indicator dict for UI dashboard."""
        job = self.scheduler.get_job(self.job_id) if self.scheduler.running else None
        next_run = str(job.next_run_time.strftime("%Y-%m-%d %H:%M:%S")) if job and job.next_run_time else "None"

        return {
            "is_running": self._is_running and self.scheduler.running,
            "status": "Active" if (self._is_running and self.scheduler.running) else "Inactive",
            "color": "green" if (self._is_running and self.scheduler.running) else "gray",
            "next_run": next_run,
        }


# Singleton instance
global_scheduler = CampaignScheduler()
