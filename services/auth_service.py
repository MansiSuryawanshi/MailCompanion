"""
services/auth_service.py - Google OAuth 2.0 Authentication Service
"""
import os
from typing import Any, Dict, Optional
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from constants import CLIENT_SECRET_FILE, GOOGLE_SCOPES, TOKEN_FILE
from utils.logger import log_campaign_action


class AuthService:
    """Manages Google OAuth2 authentication lifecycle for Gmail and Sheets API."""

    def __init__(self, client_secret_path: str = CLIENT_SECRET_FILE, token_path: str = TOKEN_FILE):
        self.client_secret_path = client_secret_path
        self.token_path = token_path
        self.credentials: Optional[Credentials] = None

    def get_credentials(self) -> Optional[Credentials]:
        """
        Retrieves valid Google OAuth2 credentials.
        Attempts to load cached token.json, refresh if expired, or returns None if re-auth required.
        """
        creds = None
        if os.path.exists(self.token_path):
            try:
                creds = Credentials.from_authorized_user_file(self.token_path, GOOGLE_SCOPES)
            except Exception as e:
                log_campaign_action("AuthService", status="WARNING", error=str(e), message="Failed to parse token.json")
                creds = None

        if creds and creds.valid:
            self.credentials = creds
            return creds

        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                with open(self.token_path, "w", encoding="utf-8") as token_file:
                    token_file.write(creds.to_json())
                self.credentials = creds
                log_campaign_action("AuthService", status="INFO", message="OAuth token refreshed successfully")
                return creds
            except Exception as e:
                log_campaign_action("AuthService", status="WARNING", error=str(e), message="Failed to refresh OAuth token")

        return None

    def authenticate_interactive(self, port: int = 0) -> Optional[Credentials]:
        """
        Launches browser-based OAuth flow using client_secret.json.
        """
        if not os.path.exists(self.client_secret_path):
            raise FileNotFoundError(
                f"Google Client Secrets file not found at '{self.client_secret_path}'. "
                "Please download client_secret.json from Google Cloud Console and place it in credentials/"
            )

        flow = InstalledAppFlow.from_client_secrets_file(
            self.client_secret_path, scopes=GOOGLE_SCOPES
        )
        creds = flow.run_local_server(port=port, prompt="consent", access_type="offline")

        os.makedirs(os.path.dirname(self.token_path), exist_ok=True)
        with open(self.token_path, "w", encoding="utf-8") as token_file:
            token_file.write(creds.to_json())

        self.credentials = creds
        log_campaign_action("AuthService", status="SUCCESS", message="Interactive OAuth authentication completed")
        return creds

    def get_user_profile(self) -> Dict[str, Any]:
        email = self.get_user_email()
        return {"email": email}

    def get_user_email(self) -> Optional[str]:
        """Fetches the authenticated user's email address from Gmail API."""
        creds = self.get_credentials()
        if not creds:
            return None
        try:
            service = build("gmail", "v1", credentials=creds)
            profile = service.users().getProfile(userId="me").execute()
            return profile.get("emailAddress")
        except Exception as e:
            log_campaign_action("AuthService", status="ERROR", error=str(e), message="Failed to fetch user email profile")
            return None

    def get_auth_status(self) -> Dict[str, Any]:
        """
        Checks overall authentication health for dashboard indicators.
        """
        has_client_secret = os.path.exists(self.client_secret_path)
        creds = self.get_credentials()

        if creds and creds.valid:
            user_email = self.get_user_email()
            return {
                "status": "Connected",
                "color": "green",
                "email": user_email or "Authenticated User",
                "client_secret_present": has_client_secret,
                "token_valid": True,
            }
        elif has_client_secret:
            return {
                "status": "Needs Auth",
                "color": "yellow",
                "email": "Not Authenticated",
                "client_secret_present": True,
                "token_valid": False,
            }
        else:
            return {
                "status": "Missing Credentials",
                "color": "red",
                "email": "No client_secret.json",
                "client_secret_present": False,
                "token_valid": False,
            }
