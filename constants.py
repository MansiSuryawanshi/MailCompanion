"""
constants.py - Application Constants, Enums, and Configuration Defaults
"""
from enum import Enum
from typing import Dict, List, Set

class CampaignStatus(str, Enum):
    PENDING = "Pending"
    SENT = "Sent"
    FOLLOWUP_SENT = "Follow-up Sent"
    SKIPPED = "Skipped"
    FAILED = "Failed"
    RESPONDED = "Responded"
    INVALID_EMAIL = "Invalid Email"
    DRAFT_CREATED = "Draft Created"

class CampaignState(str, Enum):
    DRAFT = "Draft"
    RUNNING = "Running"
    PAUSED = "Paused"
    COMPLETED = "Completed"
    ARCHIVED = "Archived"

# Required User Source Columns
COL_FIRST_NAME = "First Name"
COL_EMAIL = "Email"
COL_VERIFIED = "Verified"
COL_RESPONSE_GOT = "Response Got"

# Automatic System Columns
COL_EMAIL_SENT_DATE = "Email Sent Date & Time"
COL_FOLLOWUP_SENT_DATE = "Follow-up Sent Date & Time"
COL_STATUS = "Status"
COL_LAST_ERROR = "Last Error"
COL_LAST_UPDATED = "Last Updated"
COL_ATTEMPT_COUNT = "Attempt Count"
COL_NEXT_FOLLOWUP_DATE = "Next Follow-up Date"
COL_GMAIL_MESSAGE_ID = "Gmail Message ID"
COL_GMAIL_THREAD_ID = "Gmail Thread ID"

AUTOMATIC_COLUMNS: List[str] = [
    COL_EMAIL_SENT_DATE,
    COL_FOLLOWUP_SENT_DATE,
    COL_STATUS,
    COL_LAST_ERROR,
    COL_LAST_UPDATED,
    COL_ATTEMPT_COUNT,
    COL_NEXT_FOLLOWUP_DATE,
    COL_GMAIL_MESSAGE_ID,
    COL_GMAIL_THREAD_ID,
]

USER_PROTECTED_COLUMNS: Set[str] = {
    COL_RESPONSE_GOT,
}

# Alternate header names accepted in place of the canonical column name.
# Lets a sheet keep its own labels (e.g. "Name") without renaming to "First Name".
COLUMN_ALIASES: Dict[str, List[str]] = {
    COL_FIRST_NAME: ["Name"],
    COL_VERIFIED: ["Email Verified"],
}

VERIFICATION_TRUTHS: Set[str] = {
    "true", "yes", "1", "y", "verified"
}

# OAuth Scopes
GOOGLE_SCOPES: List[str] = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/userinfo.email",
    "openid",
]

# System Defaults
DEFAULT_MIN_SEND_DELAY = 3.0  # seconds
DEFAULT_MAX_SEND_DELAY = 7.0  # seconds
DEFAULT_FOLLOWUP_DAYS = 3      # days
DEFAULT_BATCH_SIZE = 20        # rows before sheet update flush
DEFAULT_DAILY_LIMIT = 100      # max emails per day
DEFAULT_TIMEZONE = "UTC"

# Data Sources
DATA_SOURCE_GOOGLE_SHEETS = "google_sheets"
DATA_SOURCE_SQLITE = "sqlite"

# Application Paths
DATA_DIR = "data"
CREDENTIALS_DIR = "credentials"
LOGS_DIR = "logs"
CLIENT_SECRET_FILE = "credentials/client_secret.json"
TOKEN_FILE = "credentials/token.json"
SETTINGS_FILE = "data/settings.json"
CAMPAIGNS_FILE = "data/campaigns.json"
DB_FILE = "data/contacts.db"
CACHE_FILE = "data/cache.json"
LOG_FILE = "logs/campaign.log"
