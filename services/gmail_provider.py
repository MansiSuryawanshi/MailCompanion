"""
services/gmail_provider.py - Gmail API Implementation with Threading & Draft Mode Support
"""
import base64
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Dict, Optional
from googleapiclient.discovery import build

from services.auth_service import AuthService
from services.email_provider import EmailProvider
from utils.logger import log_campaign_action


class GmailProvider(EmailProvider):
    """
    Gmail API provider implementation supporting HTML emails, Gmail conversation threading, and Draft creation.
    """

    def __init__(self, auth_service: AuthService):
        self.auth_service = auth_service

    def _get_service(self):
        creds = self.auth_service.get_credentials()
        if not creds:
            raise ValueError("Authentication credentials are not valid or expired.")
        return build("gmail", "v1", credentials=creds)

    def _build_mime_message(
        self,
        to_email: str,
        subject: str,
        body_html: str,
        sender_name: Optional[str] = None,
        in_reply_to: Optional[str] = None,
    ) -> MIMEMultipart:
        message = MIMEMultipart("alternative")
        message["To"] = to_email
        message["Subject"] = subject

        sender_email = self.auth_service.get_user_email() or "me"
        if sender_name:
            message["From"] = f"{sender_name} <{sender_email}>"
        else:
            message["From"] = sender_email

        if in_reply_to:
            message["In-Reply-To"] = in_reply_to
            message["References"] = in_reply_to

        # Attach Plain Text Fallback & HTML Content
        text_content = body_html.replace("<br>", "\n").replace("<p>", "").replace("</p>", "\n")
        part_text = MIMEText(text_content, "plain", "utf-8")
        part_html = MIMEText(body_html, "html", "utf-8")

        message.attach(part_text)
        message.attach(part_html)

        return message

    def send_email(
        self,
        to_email: str,
        subject: str,
        body_html: str,
        sender_name: Optional[str] = None,
        thread_id: Optional[str] = None,
        in_reply_to: Optional[str] = None,
    ) -> Dict[str, Any]:
        start_time = time.time()
        try:
            service = self._get_service()
            mime_msg = self._build_mime_message(to_email, subject, body_html, sender_name, in_reply_to)
            raw_encoded = base64.urlsafe_b64encode(mime_msg.as_bytes()).decode("utf-8")

            body: Dict[str, Any] = {"raw": raw_encoded}
            if thread_id:
                body["threadId"] = thread_id

            response = service.users().messages().send(userId="me", body=body).execute()
            elapsed_ms = (time.time() - start_time) * 1000

            msg_id = response.get("id", "")
            res_thread_id = response.get("threadId", "")

            log_campaign_action(
                action="Send Email (Gmail)",
                recipient=to_email,
                status="SUCCESS",
                execution_time_ms=elapsed_ms,
                message=f"Sent email to {to_email} (Msg ID: {msg_id}, Thread ID: {res_thread_id})",
            )

            return {
                "success": True,
                "message_id": msg_id,
                "thread_id": res_thread_id,
                "error": "",
                "raw_response": response,
            }
        except Exception as e:
            elapsed_ms = (time.time() - start_time) * 1000
            err_msg = str(e)
            log_campaign_action(
                action="Send Email (Gmail)",
                recipient=to_email,
                status="FAILED",
                execution_time_ms=elapsed_ms,
                error=err_msg,
            )
            return {
                "success": False,
                "message_id": "",
                "thread_id": "",
                "error": err_msg,
                "raw_response": None,
            }

    def create_draft(
        self,
        to_email: str,
        subject: str,
        body_html: str,
        sender_name: Optional[str] = None,
        thread_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        start_time = time.time()
        try:
            service = self._get_service()
            mime_msg = self._build_mime_message(to_email, subject, body_html, sender_name)
            raw_encoded = base64.urlsafe_b64encode(mime_msg.as_bytes()).decode("utf-8")

            message_body: Dict[str, Any] = {"raw": raw_encoded}
            if thread_id:
                message_body["threadId"] = thread_id

            draft_body = {"message": message_body}
            response = service.users().drafts().create(userId="me", body=draft_body).execute()
            elapsed_ms = (time.time() - start_time) * 1000

            draft_id = response.get("id", "")
            res_thread_id = response.get("message", {}).get("threadId", "")

            log_campaign_action(
                action="Create Draft (Gmail)",
                recipient=to_email,
                status="SUCCESS",
                execution_time_ms=elapsed_ms,
                message=f"Created draft for {to_email} (Draft ID: {draft_id})",
            )

            return {
                "success": True,
                "draft_id": draft_id,
                "thread_id": res_thread_id,
                "error": "",
                "raw_response": response,
            }
        except Exception as e:
            elapsed_ms = (time.time() - start_time) * 1000
            err_msg = str(e)
            log_campaign_action(
                action="Create Draft (Gmail)",
                recipient=to_email,
                status="FAILED",
                execution_time_ms=elapsed_ms,
                error=err_msg,
            )
            return {
                "success": False,
                "draft_id": "",
                "thread_id": "",
                "error": err_msg,
                "raw_response": None,
            }

    def test_connection(self) -> Dict[str, Any]:
        try:
            service = self._get_service()
            profile = service.users().getProfile(userId="me").execute()
            return {
                "status": "Connected",
                "color": "green",
                "email": profile.get("emailAddress"),
                "total_messages": profile.get("messagesTotal"),
            }
        except Exception as e:
            return {"status": "Error", "color": "red", "error": str(e)}
