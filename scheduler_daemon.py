import os
import sys
import json
import time
from datetime import datetime

# Ensure we can import from project root
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from config import ConfigManager
from scheduler import CampaignScheduler
from utils.logger import log_campaign_action

STATUS_FILE = "data/scheduler_status.json"

def update_status(pid: int, scheduler_time: str, next_run: str, is_running: bool):
    try:
        os.makedirs("data", exist_ok=True)
        status = {
            "pid": pid,
            "scheduler_time": scheduler_time,
            "next_run": next_run,
            "is_running": is_running,
            "last_updated": datetime.now().isoformat()
        }
        with open(STATUS_FILE, "w", encoding="utf-8") as f:
            json.dump(status, f, indent=4)
    except Exception as e:
        print(f"Error writing status file: {e}")

def main():
    log_campaign_action("SchedulerDaemon", status="INFO", message="Scheduler daemon starting...")
    
    config_manager = ConfigManager()
    sched_time = config_manager.settings.get("scheduler_time", "10:00")
    
    # Initialize campaign scheduler
    campaign_scheduler = CampaignScheduler()
    campaign_scheduler.start(sched_time)
    
    pid = os.getpid()
    
    while True:
        try:
            # Reload configuration to check for scheduler settings changes
            config_manager.reload()
            current_sched_time = config_manager.settings.get("scheduler_time", "10:00")
            
            # If the scheduled daily execution time changes, restart scheduler locally with new trigger
            if current_sched_time != sched_time:
                sched_time = current_sched_time
                campaign_scheduler.start(sched_time)
                log_campaign_action("SchedulerDaemon", status="INFO", message=f"Scheduler dynamic execution time updated to {sched_time}.")

            # Calculate true next run time instead of standard APScheduler trigger time
            next_run_dt = campaign_scheduler.calculate_next_run(datetime.now(), config_manager.settings)
            next_run = next_run_dt.strftime("%Y-%m-%d %H:%M:%S") if next_run_dt else "None"
            
            update_status(pid, sched_time, next_run, True)
        except Exception as e:
            print(f"Error updating daemon status: {e}")
            
        time.sleep(10)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log_campaign_action("SchedulerDaemon", status="INFO", message="Scheduler daemon stopped by user.")
    except Exception as e:
        log_campaign_action("SchedulerDaemon", status="ERROR", error=str(e), message="Scheduler daemon crashed.")
