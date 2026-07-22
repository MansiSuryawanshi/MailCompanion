"""
services/followup_service.py - Automated Follow-up Processing Engine with Gmail Threading
"""
import random
import time
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

from config import Campaign, ConfigManager
from constants import (
    COL_ATTEMPT_COUNT,
    COL_EMAIL,
    COL_EMAIL_SENT_DATE,
    COL_FIRST_NAME,
    COL_FOLLOWUP_SENT_DATE,
    COL_GMAIL_MESSAGE_ID,
    COL_GMAIL_THREAD_ID,
    COL_LAST_ERROR,
    COL_LAST_UPDATED,
    COL_RESPONSE_GOT,
    COL_STATUS,
    CampaignStatus,
)
from services.email_provider import EmailProvider
from services.email_service import EmailService
from services.sheets_service import SheetsService
from utils.logger import log_campaign_action


class FollowupService:
    """Evaluates eligible follow-up recipients and sends thread-grouped follow-up emails."""

    def __init__(
        self,
        email_provider: EmailProvider,
        sheets_service: SheetsService,
        email_service: EmailService,
        config_manager: ConfigManager,
    ):
        self.provider = email_provider
        self.sheets_service = sheets_service
        self.email_service = email_service
        self.config_manager = config_manager

    def find_followup_candidates(self, campaign: Campaign) -> List[Dict[str, Any]]:
        """
        Identifies contacts eligible for a follow-up email based on campaign rules:
        - Email Sent Date is present
        - Response Got is empty
        - Follow-up Sent Date is empty
        - Days since Email Sent Date >= campaign.followup_days
        """
        contacts = self.email_service.get_contacts(campaign)
        now = datetime.now()
        followup_days = campaign.followup_days

        candidates = []
        for row in contacts:
            email_sent_str = str(row.get(COL_EMAIL_SENT_DATE, "") or "").strip()
            followup_sent_str = str(row.get(COL_FOLLOWUP_SENT_DATE, "") or "").strip()
            response_got_str = str(row.get(COL_RESPONSE_GOT, "") or "").strip()

            if not email_sent_str:
                continue

            # Must NOT have received a response or already received a follow-up
            if response_got_str or followup_sent_str:
                continue

            # Parse Email Sent Date
            sent_dt = None
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d/%m/%Y %H:%M:%S", "%d/%m/%Y"):
                try:
                    sent_dt = datetime.strptime(email_sent_str, fmt)
                    break
                except ValueError:
                    pass

            if not sent_dt:
                continue

            days_passed = (now - sent_dt).total_seconds() / (24 * 3600)
            if days_passed >= followup_days:
                candidates.append(row)

        return candidates

    def execute_followups_batch(
        self,
        campaign: Campaign,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> Dict[str, Any]:
        """
        Processes and sends follow-up emails for all eligible candidates.
        Applies Gmail conversation threading using stored Gmail Thread ID.
        """
        # Build email-to-row map and auto-sync contacts from Google Sheets if configured
        self.email_service._email_to_sheet_row = {}
        sheet_contacts = None
        if campaign.spreadsheet_id:
            try:
                sheet_contacts = self.sheets_service.read_all_contacts()
                for sc in sheet_contacts:
                    email_clean = str(sc.get(COL_EMAIL, "") or "").strip().lower()
                    if email_clean and "_row_number" in sc:
                        self.email_service._email_to_sheet_row[email_clean] = sc["_row_number"]
                
                # Auto-sync to database if SQLite is the source of truth
                if campaign.data_source == "sqlite" and sheet_contacts:
                    from services.db_service import DBService
                    db_service = DBService()
                    db_service.import_contacts(campaign.id, sheet_contacts, overwrite=False)
            except Exception as e:
                log_campaign_action("FollowupService", status="WARNING", error=str(e), message="Failed to sync Google Sheet contacts before follow-up batch")

        candidates = self.find_followup_candidates(campaign)
        total_candidates = len(candidates)

        if total_candidates == 0:
            return {
                "success": True,
                "processed": 0,
                "sent": 0,
                "failed": 0,
                "message": "No contacts eligible for follow-up at this time.",
            }

        sent_count = 0
        failed_count = 0
        batch_size = self.config_manager.settings.get("batch_size", 20)
        sender_name = self.config_manager.settings.get("sender_name", "Mansi")
        avg_delay = (campaign.min_send_delay + campaign.max_send_delay) / 2.0

        for idx, row in enumerate(candidates, start=1):
            row_num = row.get("_row_number")
            email = str(row.get(COL_EMAIL, "") or "").strip()
            first_name = str(row.get(COL_FIRST_NAME, "") or "").strip()
            orig_msg_id = str(row.get(COL_GMAIL_MESSAGE_ID, "") or "").strip()
            orig_thread_id = str(row.get(COL_GMAIL_THREAD_ID, "") or "").strip()

            attempt_cnt_raw = row.get(COL_ATTEMPT_COUNT, "1")
            try:
                attempt_count = int(attempt_cnt_raw) + 1
            except ValueError:
                attempt_count = 2

            subject, body_html = self.email_service.render_email_content(campaign, row, is_followup=True)

            rem_candidates = total_candidates - idx
            eta_sec = rem_candidates * avg_delay
            if progress_callback:
                progress_callback({
                    "current": idx,
                    "total": total_candidates,
                    "progress": idx / total_candidates,
                    "contact_email": email,
                    "contact_name": first_name,
                    "sent_count": sent_count,
                    "failed_count": failed_count,
                    "eta_seconds": round(eta_sec, 1),
                })

            now_iso = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            if campaign.draft_mode:
                res = self.provider.create_draft(
                    to_email=email,
                    subject=subject,
                    body_html=body_html,
                    sender_name=sender_name,
                    thread_id=orig_thread_id or None,
                )
                if res["success"]:
                    sent_count += 1
                    self.email_service.update_row(campaign, row_num, {
                        COL_STATUS: CampaignStatus.DRAFT_CREATED.value,
                        COL_LAST_UPDATED: now_iso,
                        "_db_id": row.get("_db_id"),
                    }, email=email)
                else:
                    failed_count += 1
                    self.email_service.update_row(campaign, row_num, {
                        COL_STATUS: CampaignStatus.FAILED.value,
                        COL_LAST_ERROR: res.get("error", "Follow-up draft failed"),
                        COL_LAST_UPDATED: now_iso,
                        "_db_id": row.get("_db_id"),
                    }, email=email)
            else:
                res = self.provider.send_email(
                    to_email=email,
                    subject=subject,
                    body_html=body_html,
                    sender_name=sender_name,
                    thread_id=orig_thread_id or None,
                    in_reply_to=orig_msg_id or None,
                )
                if res["success"]:
                    sent_count += 1
                    self.email_service.update_row(campaign, row_num, {
                        COL_FOLLOWUP_SENT_DATE: now_iso,
                        COL_STATUS: CampaignStatus.FOLLOWUP_SENT.value,
                        COL_ATTEMPT_COUNT: attempt_count,
                        COL_LAST_UPDATED: now_iso,
                        COL_LAST_ERROR: "",
                        "_db_id": row.get("_db_id"),
                    }, email=email)
                else:
                    failed_count += 1
                    self.email_service.update_row(campaign, row_num, {
                        COL_STATUS: CampaignStatus.FAILED.value,
                        COL_LAST_ERROR: res.get("error", "Follow-up send failed"),
                        COL_LAST_UPDATED: now_iso,
                        "_db_id": row.get("_db_id"),
                    }, email=email)

            if (campaign.data_source != "sqlite" or campaign.spreadsheet_id) and idx % batch_size == 0:
                self.sheets_service.flush_updates()

            if idx < total_candidates:
                delay = random.uniform(campaign.min_send_delay, campaign.max_send_delay)
                time.sleep(delay)

        if campaign.data_source != "sqlite" or campaign.spreadsheet_id:
            self.sheets_service.flush_updates()

        log_campaign_action("FollowupService", status="SUCCESS", message=f"Follow-ups complete. Sent: {sent_count}, Failed: {failed_count}")

        return {
            "success": True,
            "processed": total_candidates,
            "sent": sent_count,
            "failed": failed_count,
            "message": f"Follow-up batch completed. Sent/Drafted: {sent_count}, Failed: {failed_count}",
        }
