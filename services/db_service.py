"""
services/db_service.py - SQLite Database Manager for Contact Storage & Management
"""
import json
import os
import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional
from constants import (
    AUTOMATIC_COLUMNS,
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
    COL_RESPONSE_GOT,
    COL_STATUS,
    COL_VERIFIED,
    DB_FILE,
    CampaignStatus,
)
from utils.logger import log_campaign_action


class DBService:
    """Manages local SQLite database storage for campaign contacts."""

    def __init__(self, db_path: str = DB_FILE):
        self.db_path = db_path
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        """Creates table schema if it does not exist."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS contacts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    campaign_id TEXT NOT NULL,
                    first_name TEXT DEFAULT '',
                    email TEXT NOT NULL,
                    verified TEXT DEFAULT 'Yes',
                    response_got TEXT DEFAULT '',
                    email_sent_date TEXT DEFAULT '',
                    followup_sent_date TEXT DEFAULT '',
                    status TEXT DEFAULT 'Pending',
                    last_error TEXT DEFAULT '',
                    last_updated TEXT DEFAULT '',
                    attempt_count INTEGER DEFAULT 0,
                    next_followup_date TEXT DEFAULT '',
                    gmail_message_id TEXT DEFAULT '',
                    gmail_thread_id TEXT DEFAULT '',
                    extra_json TEXT DEFAULT '{}',
                    created_at TEXT DEFAULT (datetime('now'))
                )
                """
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_campaign_email ON contacts(campaign_id, email)"
            )
            conn.commit()

    def import_contacts(
        self, campaign_id: str, records: List[Dict[str, Any]], overwrite: bool = False
    ) -> int:
        """
        Imports a list of contact dictionaries (e.g. from Excel/CSV) into SQLite.
        If overwrite is True, existing contacts for campaign_id are replaced.
        Returns total inserted count.
        """
        if not records:
            return 0

        with self._get_connection() as conn:
            cursor = conn.cursor()
            if overwrite:
                cursor.execute("DELETE FROM contacts WHERE campaign_id = ?", (campaign_id,))

            inserted = 0
            now_iso = datetime.now().isoformat()

            for rec in records:
                email = str(rec.get(COL_EMAIL) or rec.get("email") or rec.get("Email") or "").strip()
                if not email:
                    continue

                first_name = str(rec.get(COL_FIRST_NAME) or rec.get("first_name") or rec.get("First Name") or rec.get("Name") or "").strip()
                verified = str(rec.get(COL_VERIFIED) or rec.get("verified") or rec.get("Verified") or "Yes").strip()
                response_got = str(rec.get(COL_RESPONSE_GOT) or rec.get("response_got") or rec.get("Response Got") or "").strip()
                status = str(rec.get(COL_STATUS) or rec.get("status") or rec.get("Status") or CampaignStatus.PENDING.value).strip()

                email_sent_date = str(
                    rec.get(COL_EMAIL_SENT_DATE)
                    or rec.get("Email Sent Date")
                    or rec.get("email_sent_date")
                    or ""
                ).strip()
                followup_sent_date = str(
                    rec.get(COL_FOLLOWUP_SENT_DATE)
                    or rec.get("Follow-up Sent Date")
                    or rec.get("followup_sent_date")
                    or ""
                ).strip()
                last_error = str(rec.get(COL_LAST_ERROR) or "")
                attempt_count = int(rec.get(COL_ATTEMPT_COUNT) or 0)
                next_followup_date = str(rec.get(COL_NEXT_FOLLOWUP_DATE) or "")
                gmail_message_id = str(rec.get(COL_GMAIL_MESSAGE_ID) or "")
                gmail_thread_id = str(rec.get(COL_GMAIL_THREAD_ID) or "")

                # Store all remaining fields in extra_json
                known_keys = {
                    COL_EMAIL, COL_FIRST_NAME, COL_VERIFIED, COL_RESPONSE_GOT,
                    COL_STATUS, COL_EMAIL_SENT_DATE, COL_FOLLOWUP_SENT_DATE,
                    COL_LAST_ERROR, COL_LAST_UPDATED, COL_ATTEMPT_COUNT,
                    COL_NEXT_FOLLOWUP_DATE, COL_GMAIL_MESSAGE_ID, COL_GMAIL_THREAD_ID,
                    "email", "first_name", "verified", "response_got", "status",
                    "Email Sent Date", "Follow-up Sent Date", "email_sent_date", "followup_sent_date"
                }
                extra = {k: str(v) for k, v in rec.items() if k not in known_keys and not k.startswith("_")}
                extra_json_str = json.dumps(extra)

                # Check if already exists for this campaign
                cursor.execute(
                    "SELECT id FROM contacts WHERE campaign_id = ? AND email = ?",
                    (campaign_id, email),
                )
                row = cursor.fetchone()
                if row:
                    # Update existing record
                    cursor.execute(
                        """
                        UPDATE contacts SET
                            first_name = ?,
                            verified = ?,
                            response_got = ?,
                            extra_json = ?,
                            last_updated = ?
                        WHERE id = ?
                        """,
                        (first_name, verified, response_got, extra_json_str, now_iso, row["id"]),
                    )
                else:
                    # Insert new record
                    cursor.execute(
                        """
                        INSERT INTO contacts (
                            campaign_id, first_name, email, verified, response_got,
                            status, email_sent_date, followup_sent_date, last_error,
                            last_updated, attempt_count, next_followup_date,
                            gmail_message_id, gmail_thread_id, extra_json
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            campaign_id, first_name, email, verified, response_got,
                            status, email_sent_date, followup_sent_date, last_error,
                            now_iso, attempt_count, next_followup_date,
                            gmail_message_id, gmail_thread_id, extra_json_str
                        ),
                    )
                    inserted += 1

            conn.commit()

        log_campaign_action("DBService", status="SUCCESS", message=f"Imported/Updated {len(records)} contacts for campaign '{campaign_id}' ({inserted} new)")
        return inserted

    def read_all_contacts(self, campaign_id: str) -> List[Dict[str, Any]]:
        """
        Reads all contacts for a campaign from SQLite.
        Returns formatted list of dictionaries compatible with SheetsService output.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM contacts WHERE campaign_id = ? ORDER BY id ASC",
                (campaign_id,),
            )
            rows = cursor.fetchall()

        contacts = []
        for index, r in enumerate(rows, start=2):  # start=2 for row_number compatibility
            rec = {
                "_db_id": r["id"],
                "_row_number": index,
                COL_FIRST_NAME: r["first_name"] or "",
                COL_EMAIL: r["email"] or "",
                COL_VERIFIED: r["verified"] or "Yes",
                COL_RESPONSE_GOT: r["response_got"] or "",
                COL_EMAIL_SENT_DATE: r["email_sent_date"] or "",
                COL_FOLLOWUP_SENT_DATE: r["followup_sent_date"] or "",
                COL_STATUS: r["status"] or CampaignStatus.PENDING.value,
                COL_LAST_ERROR: r["last_error"] or "",
                COL_LAST_UPDATED: r["last_updated"] or "",
                COL_ATTEMPT_COUNT: str(r["attempt_count"] or 0),
                COL_NEXT_FOLLOWUP_DATE: r["next_followup_date"] or "",
                COL_GMAIL_MESSAGE_ID: r["gmail_message_id"] or "",
                COL_GMAIL_THREAD_ID: r["gmail_thread_id"] or "",
            }
            # Merge extra custom fields
            if r["extra_json"]:
                try:
                    extra = json.loads(r["extra_json"])
                    for k, v in extra.items():
                        if k not in rec:
                            rec[k] = str(v)
                except Exception:
                    pass

            contacts.append(rec)

        return contacts

    def update_row_immediately(self, campaign_id: str, row_number: int, updates: Dict[str, Any]) -> bool:
        """Updates contact row in SQLite based on _db_id or row index."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            db_id = updates.get("_db_id")
            if not db_id:
                contacts = self.read_all_contacts(campaign_id)
                target = next((c for c in contacts if c.get("_row_number") == row_number), None)
                if target:
                    db_id = target.get("_db_id")

            if not db_id:
                return False

            now_iso = datetime.now().isoformat()
            field_map = {
                COL_FIRST_NAME: "first_name",
                COL_EMAIL: "email",
                COL_VERIFIED: "verified",
                COL_RESPONSE_GOT: "response_got",
                COL_STATUS: "status",
                COL_EMAIL_SENT_DATE: "email_sent_date",
                COL_FOLLOWUP_SENT_DATE: "followup_sent_date",
                COL_LAST_ERROR: "last_error",
                COL_ATTEMPT_COUNT: "attempt_count",
                COL_NEXT_FOLLOWUP_DATE: "next_followup_date",
                COL_GMAIL_MESSAGE_ID: "gmail_message_id",
                COL_GMAIL_THREAD_ID: "gmail_thread_id",
            }

            set_clauses = ["last_updated = ?"]
            params = [now_iso]

            for key, val in updates.items():
                if key in field_map:
                    col_name = field_map[key]
                    set_clauses.append(f"{col_name} = ?")
                    params.append(val)

            params.append(db_id)
            query = f"UPDATE contacts SET {', '.join(set_clauses)} WHERE id = ?"
            cursor.execute(query, tuple(params))
            conn.commit()

        return True

    def clear_campaign_contacts(self, campaign_id: str) -> bool:
        """Deletes all contacts for a given campaign."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM contacts WHERE campaign_id = ?", (campaign_id,))
            conn.commit()
        return True
