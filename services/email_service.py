"""
services/email_service.py - Jinja2 Dynamic Templating, Dry-Run & Email Batch Dispatcher Engine
"""
import random
import time
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple
from jinja2 import Environment, BaseLoader, TemplateSyntaxError

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
    COL_NEXT_FOLLOWUP_DATE,
    COL_STATUS,
    COL_VERIFIED,
    DATA_SOURCE_SQLITE,
    CampaignStatus,
)
from services.db_service import DBService
from services.email_provider import EmailProvider
from services.sheets_service import SheetsService
from utils.logger import log_campaign_action
from utils.validator import evaluate_contact_row


def render_template_string(template_str: str, context: Dict[str, Any]) -> str:
    """
    Renders a string template using Jinja2 with custom context variables.
    """
    if not template_str:
        return ""
    try:
        env = Environment(loader=BaseLoader(), autoescape=False)
        template = env.from_string(template_str)
        return template.render(**context)
    except TemplateSyntaxError as e:
        return f"[Template Syntax Error: {e}]"
    except Exception as e:
        return f"[Template Render Error: {e}]"


class EmailService:
    """Orchestrates campaign dry-runs, test emails, dynamic rendering, and batch email dispatching."""

    def __init__(
        self,
        email_provider: EmailProvider,
        sheets_service: SheetsService,
        config_manager: ConfigManager,
    ):
        self.provider = email_provider
        self.sheets_service = sheets_service
        self.config_manager = config_manager
        self.db_service = DBService()

    def get_contacts(self, campaign: Campaign) -> List[Dict[str, Any]]:
        """Reads contacts from SQLite or Google Sheets depending on campaign data_source setting."""
        if campaign.data_source == DATA_SOURCE_SQLITE:
            return self.db_service.read_all_contacts(campaign.id)
        return self.sheets_service.read_all_contacts()

    def update_row(self, campaign: Campaign, row_num: int, updates: Dict[str, Any], email: Optional[str] = None):
        """Updates row in SQLite or queues update in Google Sheets."""
        if campaign.data_source == DATA_SOURCE_SQLITE:
            self.db_service.update_row_immediately(campaign.id, row_num, updates)
            if campaign.spreadsheet_id and email:
                email_clean = email.strip().lower()
                if hasattr(self, "_email_to_sheet_row") and email_clean in self._email_to_sheet_row:
                    sheet_row_num = self._email_to_sheet_row[email_clean]
                    sheet_updates = {k: v for k, v in updates.items() if k != "_db_id"}
                    self.sheets_service.queue_row_update(sheet_row_num, sheet_updates)
        else:
            self.sheets_service.queue_row_update(row_num, updates)

    def build_context(self, row: Dict[str, Any], sender_name: str) -> Dict[str, Any]:
        """Builds template context dictionary from contact row and system values."""
        now_str = datetime.now().strftime("%B %d, %Y")
        ctx = {
            "first_name": row.get(COL_FIRST_NAME, ""),
            "email": row.get(COL_EMAIL, ""),
            "current_date": now_str,
            "sender_name": sender_name,
        }
        # Inject all other row columns dynamically
        for key, val in row.items():
            if not key.startswith("_") and key not in ctx:
                ctx[key] = val
        return ctx

    def render_email_content(
        self, campaign: Campaign, row: Dict[str, Any], is_followup: bool = False
    ) -> Tuple[str, str]:
        """Renders Subject and Body HTML for a specific contact row."""
        sender_name = self.config_manager.settings.get("sender_name", "Mansi")
        signature = self.config_manager.settings.get("email_signature", "")
        context = self.build_context(row, sender_name)

        if is_followup:
            subject_tmpl = campaign.followup_subject
            body_tmpl = campaign.followup_body
        else:
            subject_tmpl = campaign.initial_subject
            body_tmpl = campaign.initial_body

        subject = render_template_string(subject_tmpl, context)
        body_content = render_template_string(body_tmpl, context)

        # Append signature if configured and not already included
        if signature and signature not in body_content:
            body_html = f"{body_content}<br>{signature}"
        else:
            body_html = body_content

        return subject, body_html

    def send_test_email(
        self, campaign: Campaign, test_recipient: str, is_followup: bool = False
    ) -> Dict[str, Any]:
        """Sends a test email to the user without modifying Google Sheet."""
        sample_row = {
            COL_FIRST_NAME: "John",
            COL_EMAIL: test_recipient,
            COL_VERIFIED: "Yes",
        }
        subject, body_html = self.render_email_content(campaign, sample_row, is_followup=is_followup)
        sender_name = self.config_manager.settings.get("sender_name", "Mansi")

        return self.provider.send_email(
            to_email=test_recipient,
            subject=f"[TEST] {subject}",
            body_html=body_html,
            sender_name=sender_name,
        )

    def run_dry_run(self, campaign: Campaign) -> Dict[str, Any]:
        """
        Executes a dry-run analysis over all contacts without sending emails.
        Returns summary report including Will Send, Skipped, Invalid, and Estimated Duration.
        """
        # Auto-sync Google Sheet contacts to SQLite if SQLite is source and Google Sheet link exists
        if campaign.data_source == DATA_SOURCE_SQLITE and campaign.spreadsheet_id:
            try:
                sheet_contacts = self.sheets_service.read_all_contacts()
                if sheet_contacts:
                    self.db_service.import_contacts(campaign.id, sheet_contacts, overwrite=False)
            except Exception as e:
                log_campaign_action("EmailService", status="WARNING", error=str(e), message="Failed to auto-sync Google Sheet contacts before dry run")

        contacts = self.get_contacts(campaign)
        seen_emails = set()

        will_send = []
        skipped = []
        already_sent = []
        invalid = []

        min_delay = campaign.min_send_delay
        max_delay = campaign.max_send_delay
        avg_delay = (min_delay + max_delay) / 2.0

        for row in contacts:
            eval_res = evaluate_contact_row(row, seen_emails)
            email_sent_date = str(row.get(COL_EMAIL_SENT_DATE, "") or "").strip()
            current_status = str(row.get(COL_STATUS, "") or "").strip()

            entry = {
                "row_number": row.get("_row_number"),
                "first_name": row.get(COL_FIRST_NAME, ""),
                "email": row.get(COL_EMAIL, ""),
                "status": current_status or CampaignStatus.PENDING.value,
                "reason": eval_res["reason"],
            }

            if not eval_res["valid_email"]:
                entry["action"] = "Skipped"
                invalid.append(entry)
            elif email_sent_date or current_status in (CampaignStatus.SENT.value, CampaignStatus.FOLLOWUP_SENT.value):
                entry["action"] = "Already Sent"
                entry["reason"] = f"Sent on {email_sent_date}"
                already_sent.append(entry)
            elif not eval_res["can_send"]:
                entry["action"] = "Skipped"
                skipped.append(entry)
            else:
                entry["action"] = "Will Send"
                will_send.append(entry)

        total_will_send = len(will_send)
        est_seconds = total_will_send * avg_delay

        return {
            "total_contacts": len(contacts),
            "will_send_count": total_will_send,
            "already_sent_count": len(already_sent),
            "skipped_count": len(skipped),
            "invalid_count": len(invalid),
            "estimated_duration_sec": round(est_seconds, 1),
            "will_send": will_send,
            "already_sent": already_sent,
            "skipped": skipped,
            "invalid": invalid,
        }

    def execute_campaign_batch(
        self,
        campaign: Campaign,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
        retry_failed_only: bool = False,
    ) -> Dict[str, Any]:
        """
        Executes campaign batch email dispatching.
        Updates contacts with batch buffering. Supports progress callbacks.
        """
        # Fetch and sync Google Sheet contacts if configured
        self._email_to_sheet_row = {}
        sheet_contacts = None
        if campaign.spreadsheet_id:
            try:
                sheet_contacts = self.sheets_service.read_all_contacts()
                for sc in sheet_contacts:
                    email_clean = str(sc.get(COL_EMAIL, "") or "").strip().lower()
                    if email_clean and "_row_number" in sc:
                        self._email_to_sheet_row[email_clean] = sc["_row_number"]
                
                # Auto-sync to database if SQLite is the source of truth
                if campaign.data_source == DATA_SOURCE_SQLITE and sheet_contacts:
                    self.db_service.import_contacts(campaign.id, sheet_contacts, overwrite=False)
            except Exception as e:
                log_campaign_action("EmailService", status="WARNING", error=str(e), message="Failed to sync Google Sheet contacts before campaign batch")

        contacts = self.get_contacts(campaign)
        seen_emails = set()

        # Identify targets
        targets = []
        for row in contacts:
            eval_res = evaluate_contact_row(row, seen_emails)
            sent_date = str(row.get(COL_EMAIL_SENT_DATE, "") or "").strip()
            status = str(row.get(COL_STATUS, "") or "").strip()

            if retry_failed_only:
                if status == CampaignStatus.FAILED.value:
                    targets.append(row)
            else:
                # Normal run: send if verified, valid, name present, not sent yet
                if eval_res["can_send"] and not sent_date and status not in (CampaignStatus.SENT.value, CampaignStatus.FOLLOWUP_SENT.value):
                    targets.append(row)

        total_targets = len(targets)
        if total_targets == 0:
            return {"success": True, "processed": 0, "sent": 0, "failed": 0, "message": "No pending contacts to process."}

        sent_count = 0
        failed_count = 0
        batch_size = self.config_manager.settings.get("batch_size", 20)
        sender_name = self.config_manager.settings.get("sender_name", "Mansi")

        avg_delay = (campaign.min_send_delay + campaign.max_send_delay) / 2.0

        for idx, row in enumerate(targets, start=1):
            row_num = row.get("_row_number")
            email = str(row.get(COL_EMAIL, "") or "").strip()
            first_name = str(row.get(COL_FIRST_NAME, "") or "").strip()

            subject, body_html = self.render_email_content(campaign, row, is_followup=False)

            # Inform callback
            rem_targets = total_targets - idx
            eta_sec = rem_targets * avg_delay
            if progress_callback:
                progress_callback({
                    "current": idx,
                    "total": total_targets,
                    "progress": idx / total_targets,
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
                )
                if res["success"]:
                    sent_count += 1
                    self.update_row(campaign, row_num, {
                        COL_STATUS: CampaignStatus.DRAFT_CREATED.value,
                        COL_LAST_UPDATED: now_iso,
                        COL_GMAIL_MESSAGE_ID: res.get("draft_id", ""),
                        COL_GMAIL_THREAD_ID: res.get("thread_id", ""),
                        "_db_id": row.get("_db_id"),
                    }, email=email)
                else:
                    failed_count += 1
                    self.update_row(campaign, row_num, {
                        COL_STATUS: CampaignStatus.FAILED.value,
                        COL_LAST_ERROR: res.get("error", "Draft creation failed"),
                        COL_LAST_UPDATED: now_iso,
                        "_db_id": row.get("_db_id"),
                    }, email=email)
            else:
                res = self.provider.send_email(
                    to_email=email,
                    subject=subject,
                    body_html=body_html,
                    sender_name=sender_name,
                )
                if res["success"]:
                    sent_count += 1
                    self.update_row(campaign, row_num, {
                        COL_EMAIL_SENT_DATE: now_iso,
                        COL_STATUS: CampaignStatus.SENT.value,
                        COL_ATTEMPT_COUNT: 1,
                        COL_LAST_UPDATED: now_iso,
                        COL_LAST_ERROR: "",
                        COL_GMAIL_MESSAGE_ID: res.get("message_id", ""),
                        COL_GMAIL_THREAD_ID: res.get("thread_id", ""),
                        "_db_id": row.get("_db_id"),
                    }, email=email)
                else:
                    failed_count += 1
                    self.update_row(campaign, row_num, {
                        COL_STATUS: CampaignStatus.FAILED.value,
                        COL_LAST_ERROR: res.get("error", "Send failed"),
                        COL_LAST_UPDATED: now_iso,
                        "_db_id": row.get("_db_id"),
                    }, email=email)

            # Flush batch updates every N items if Google Sheets
            if (campaign.data_source != DATA_SOURCE_SQLITE or campaign.spreadsheet_id) and idx % batch_size == 0:
                self.sheets_service.flush_updates()

            # Randomized send delay
            if idx < total_targets:
                delay = random.uniform(campaign.min_send_delay, campaign.max_send_delay)
                time.sleep(delay)

        # Flush remaining queued updates
        if campaign.data_source != DATA_SOURCE_SQLITE or campaign.spreadsheet_id:
            self.sheets_service.flush_updates()

        campaign.last_email_sent_time = datetime.now().isoformat()
        self.config_manager.update_campaign(campaign)

        return {
            "success": True,
            "processed": total_targets,
            "sent": sent_count,
            "failed": failed_count,
            "message": f"Batch completed. Sent/Drafted: {sent_count}, Failed: {failed_count}",
        }

    def reset_campaign(self, campaign: Campaign) -> bool:
        """
        Resets all contact send statuses, sent dates, and attempt counts 
        for the given campaign so that emails can be sent again.
        """
        now_iso = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        updates = {
            COL_EMAIL_SENT_DATE: "",
            COL_FOLLOWUP_SENT_DATE: "",
            COL_STATUS: CampaignStatus.PENDING.value,
            COL_LAST_ERROR: "",
            COL_ATTEMPT_COUNT: 0,
            COL_NEXT_FOLLOWUP_DATE: "",
            COL_GMAIL_MESSAGE_ID: "",
            COL_GMAIL_THREAD_ID: "",
            COL_LAST_UPDATED: now_iso,
        }

        # 1. Reset SQLite DB if SQLite is the source
        if campaign.data_source == DATA_SOURCE_SQLITE:
            self.db_service.reset_campaign_contacts(campaign.id)

        # 2. Reset Google Sheet if it's the primary source or configured as secondary
        if campaign.data_source != DATA_SOURCE_SQLITE:
            contacts = self.get_contacts(campaign)
            for row in contacts:
                row_num = row.get("_row_number")
                if row_num:
                    self.sheets_service.queue_row_update(row_num, updates)
            self.sheets_service.flush_updates()
        elif campaign.spreadsheet_id:
            # SQLite campaign with configured Google Sheet link
            try:
                sheet_contacts = self.sheets_service.read_all_contacts()
                email_to_row = {}
                for sc in sheet_contacts:
                    email_clean = str(sc.get(COL_EMAIL, "") or "").strip().lower()
                    if email_clean and "_row_number" in sc:
                        email_to_row[email_clean] = sc["_row_number"]

                contacts = self.get_contacts(campaign)
                for row in contacts:
                    email = str(row.get(COL_EMAIL, "") or "").strip()
                    email_clean = email.lower()
                    if email_clean in email_to_row:
                        sheet_row_num = email_to_row[email_clean]
                        self.sheets_service.queue_row_update(sheet_row_num, updates)
                self.sheets_service.flush_updates()
            except Exception as e:
                log_campaign_action("EmailService", status="WARNING", error=str(e), message="Failed to reset Google Sheet rows")

        # 3. Log the reset action
        log_campaign_action("EmailService", status="SUCCESS", message=f"Campaign '{campaign.id}' email send states reset")
        return True
