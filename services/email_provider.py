"""
services/email_provider.py - Abstract Email Provider Interface
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


class EmailProvider(ABC):
    """
    Abstract interface for email backends (Gmail, Outlook, Amazon SES, SendGrid).
    """

    @abstractmethod
    def send_email(
        self,
        to_email: str,
        subject: str,
        body_html: str,
        sender_name: Optional[str] = None,
        thread_id: Optional[str] = None,
        in_reply_to: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Sends an email message.
        Returns dict: {'success': bool, 'message_id': str, 'thread_id': str, 'error': str}
        """
        pass

    @abstractmethod
    def create_draft(
        self,
        to_email: str,
        subject: str,
        body_html: str,
        sender_name: Optional[str] = None,
        thread_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Creates an email draft in the provider mailbox without sending.
        Returns dict: {'success': bool, 'draft_id': str, 'thread_id': str, 'error': str}
        """
        pass

    @abstractmethod
    def test_connection(self) -> Dict[str, Any]:
        """
        Tests provider authentication and connection health.
        """
        pass
