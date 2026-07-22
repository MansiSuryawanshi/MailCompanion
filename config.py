"""
config.py - Application Configuration & Multi-Campaign Settings Manager
"""
import json
import os
import re
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, asdict, field

from constants import (
    CAMPAIGNS_FILE,
    DATA_DIR,
    DATA_SOURCE_GOOGLE_SHEETS,
    DATA_SOURCE_SQLITE,
    DEFAULT_BATCH_SIZE,
    DEFAULT_DAILY_LIMIT,
    DEFAULT_FOLLOWUP_DAYS,
    DEFAULT_MAX_SEND_DELAY,
    DEFAULT_MIN_SEND_DELAY,
    DEFAULT_TIMEZONE,
    SETTINGS_FILE,
    CampaignState,
)


def extract_spreadsheet_id(url_or_id: str) -> str:
    """
    Extracts the 44-character Google Spreadsheet ID from a URL or raw ID string.
    """
    if not url_or_id:
        return ""
    url_or_id = url_or_id.strip()
    match = re.search(r"/spreadsheets/d/([a-zA-Z0-9-_]+)", url_or_id)
    if match:
        return match.group(1)
    # If no URL pattern matched, assume it's the ID if alphanumeric with hyphens/underscores
    if re.match(r"^[a-zA-Z0-9-_]{20,}$", url_or_id):
        return url_or_id
    return url_or_id


def ensure_directories():
    """Ensure data, credentials, and logs directories exist."""
    for directory in ["data", "credentials", "logs"]:
        os.makedirs(directory, exist_ok=True)


@dataclass
class Campaign:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = "Default Campaign"
    spreadsheet_url: str = ""
    spreadsheet_id: str = ""
    initial_subject: str = "Exclusive Opportunity for {{first_name}}"
    initial_body: str = (
        "<p>Hi {{first_name}},</p>\n"
        "<p>I came across your work and would love to connect regarding an exciting project.</p>\n"
        "<p>Best regards,<br>{{sender_name}}</p>"
    )
    followup_subject: str = "Re: Exclusive Opportunity for {{first_name}}"
    followup_body: str = (
        "<p>Hi {{first_name}},</p>\n"
        "<p>Following up on my previous message. Let me know if you have a few minutes to chat.</p>\n"
        "<p>Best regards,<br>{{sender_name}}</p>"
    )
    min_send_delay: float = DEFAULT_MIN_SEND_DELAY
    max_send_delay: float = DEFAULT_MAX_SEND_DELAY
    followup_days: int = DEFAULT_FOLLOWUP_DAYS
    daily_limit: int = DEFAULT_DAILY_LIMIT
    draft_mode: bool = False
    data_source: str = "sqlite"  # "sqlite" or "google_sheets"
    state: str = CampaignState.DRAFT.value
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    last_sync_time: str = ""
    last_email_sent_time: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Campaign":
        # Handle Spreadsheet ID extraction on load
        if "spreadsheet_url" in data and not data.get("spreadsheet_id"):
            data["spreadsheet_id"] = extract_spreadsheet_id(data["spreadsheet_url"])
        valid_keys = cls.__dataclass_fields__.keys()
        filtered = {k: v for k, v in data.items() if k in valid_keys}
        return cls(**filtered)


class ConfigManager:
    """Manages global application settings and multi-campaign persistence."""

    def __init__(self):
        ensure_directories()
        self.settings_file = SETTINGS_FILE
        self.campaigns_file = CAMPAIGNS_FILE
        self.settings: Dict[str, Any] = self._load_settings()
        self.campaigns: Dict[str, Campaign] = self._load_campaigns()
        self._ensure_default_campaign()

    def _load_settings(self) -> Dict[str, Any]:
        default_settings = {
            "sender_name": "Mansi",
            "email_signature": "<p>--<br><strong>Mansi</strong><br>Email Campaign Manager</p>",
            "timezone": DEFAULT_TIMEZONE,
            "min_send_delay": DEFAULT_MIN_SEND_DELAY,
            "max_send_delay": DEFAULT_MAX_SEND_DELAY,
            "followup_days": DEFAULT_FOLLOWUP_DAYS,
            "batch_size": DEFAULT_BATCH_SIZE,
            "daily_limit": DEFAULT_DAILY_LIMIT,
            "draft_mode": False,
            "active_campaign_id": "",
            "scheduler_enabled": False,
            "scheduler_time": "10:00",
            "theme": "Dark",
        }
        if os.path.exists(self.settings_file):
            try:
                with open(self.settings_file, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                    default_settings.update(saved)
            except Exception as e:
                print(f"Error loading settings.json: {e}")
        return default_settings

    def save_settings(self) -> None:
        """Persist settings to JSON file."""
        ensure_directories()
        with open(self.settings_file, "w", encoding="utf-8") as f:
            json.dump(self.settings, f, indent=4)

    def _load_campaigns(self) -> Dict[str, Campaign]:
        campaigns: Dict[str, Campaign] = {}
        if os.path.exists(self.campaigns_file):
            try:
                with open(self.campaigns_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for c_id, c_data in data.items():
                        campaigns[c_id] = Campaign.from_dict(c_data)
            except Exception as e:
                print(f"Error loading campaigns.json: {e}")
        return campaigns

    def save_campaigns(self) -> None:
        """Persist campaigns to JSON file."""
        ensure_directories()
        serialized = {c_id: c.to_dict() for c_id, c in self.campaigns.items()}
        with open(self.campaigns_file, "w", encoding="utf-8") as f:
            json.dump(serialized, f, indent=4)

    def _ensure_default_campaign(self) -> None:
        if not self.campaigns:
            default_campaign = Campaign(name="Default Campaign")
            self.campaigns[default_campaign.id] = default_campaign
            self.settings["active_campaign_id"] = default_campaign.id
            self.save_campaigns()
            self.save_settings()
        elif not self.settings.get("active_campaign_id") or self.settings["active_campaign_id"] not in self.campaigns:
            self.settings["active_campaign_id"] = next(iter(self.campaigns.keys()))
            self.save_settings()

    def get_active_campaign(self) -> Campaign:
        active_id = self.settings.get("active_campaign_id", "")
        if active_id in self.campaigns:
            return self.campaigns[active_id]
        # Return fallback
        return next(iter(self.campaigns.values()))

    def set_active_campaign(self, campaign_id: str) -> bool:
        if campaign_id in self.campaigns:
            self.settings["active_campaign_id"] = campaign_id
            self.save_settings()
            return True
        return False

    def create_campaign(self, name: str, spreadsheet_url: str = "") -> Campaign:
        sp_id = extract_spreadsheet_id(spreadsheet_url)
        new_campaign = Campaign(
            name=name,
            spreadsheet_url=spreadsheet_url,
            spreadsheet_id=sp_id,
            data_source=DATA_SOURCE_GOOGLE_SHEETS if sp_id else DATA_SOURCE_SQLITE,
        )
        self.campaigns[new_campaign.id] = new_campaign
        self.settings["active_campaign_id"] = new_campaign.id
        self.save_campaigns()
        self.save_settings()
        return new_campaign

    def update_campaign(self, campaign: Campaign) -> None:
        campaign.spreadsheet_id = extract_spreadsheet_id(campaign.spreadsheet_url)
        self.campaigns[campaign.id] = campaign
        self.save_campaigns()

    def duplicate_campaign(self, campaign_id: str) -> Optional[Campaign]:
        if campaign_id not in self.campaigns:
            return None
        orig = self.campaigns[campaign_id]
        dup_data = orig.to_dict()
        dup_data["id"] = str(uuid.uuid4())
        dup_data["name"] = f"{orig.name} (Copy)"
        dup_data["state"] = CampaignState.DRAFT.value
        dup_data["created_at"] = datetime.now().isoformat()
        dup = Campaign.from_dict(dup_data)
        self.campaigns[dup.id] = dup
        self.save_campaigns()
        return dup

    def delete_campaign(self, campaign_id: str) -> bool:
        if campaign_id in self.campaigns and len(self.campaigns) > 1:
            del self.campaigns[campaign_id]
            if self.settings.get("active_campaign_id") == campaign_id:
                self.settings["active_campaign_id"] = next(iter(self.campaigns.keys()))
            self.save_campaigns()
            self.save_settings()
            return True
        return False

    def export_all_config(self) -> Dict[str, Any]:
        """Export all settings and campaigns as a JSON serializable dict for backup."""
        return {
            "version": "1.0",
            "exported_at": datetime.now().isoformat(),
            "settings": self.settings,
            "campaigns": {c_id: c.to_dict() for c_id, c in self.campaigns.items()},
        }

    def import_all_config(self, data: Dict[str, Any]) -> bool:
        """Import settings and campaigns backup."""
        try:
            if "settings" in data and isinstance(data["settings"], dict):
                self.settings.update(data["settings"])
                self.save_settings()
            if "campaigns" in data and isinstance(data["campaigns"], dict):
                for c_id, c_data in data["campaigns"].items():
                    self.campaigns[c_id] = Campaign.from_dict(c_data)
                self.save_campaigns()
            return True
        except Exception as e:
            print(f"Error importing configuration: {e}")
            return False
