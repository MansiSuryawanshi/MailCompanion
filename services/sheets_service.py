"""
services/sheets_service.py - Google Sheets API Integration & Schema Management Service
"""
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
import gspread
from gspread.cell import Cell

from constants import (
    AUTOMATIC_COLUMNS,
    COL_EMAIL,
    COL_EMAIL_SENT_DATE,
    COL_FIRST_NAME,
    COL_FOLLOWUP_SENT_DATE,
    COL_RESPONSE_GOT,
    COL_VERIFIED,
    COLUMN_ALIASES,
    USER_PROTECTED_COLUMNS,
)
from services.auth_service import AuthService
from utils.logger import log_campaign_action


class SheetsService:
    """Handles read/write operations, schema auto-healing, and batch updates for Google Sheets."""

    def __init__(self, auth_service: AuthService, spreadsheet_id: str):
        self.auth_service = auth_service
        self.spreadsheet_id = spreadsheet_id
        self.gc: Optional[gspread.Client] = None
        self.spreadsheet: Optional[gspread.Spreadsheet] = None
        self.worksheet: Optional[gspread.Worksheet] = None
        self.header_map: Dict[str, int] = {}  # Column Name -> 1-based Column Index
        self.update_queue: List[Cell] = []    # Batch updates queue

    def connect(self) -> bool:
        """Establishes connection to Google Sheets API and selects first worksheet."""
        creds = self.auth_service.get_credentials()
        if not creds:
            log_campaign_action("SheetsService", status="ERROR", error="No valid Google credentials")
            return False

        try:
            self.gc = gspread.authorize(creds)
            self.spreadsheet = self.gc.open_by_key(self.spreadsheet_id)
            self.worksheet = self.spreadsheet.get_worksheet(0)
            self._ensure_schema()
            log_campaign_action("SheetsService", status="SUCCESS", message=f"Connected to sheet ID '{self.spreadsheet_id}'")
            return True
        except Exception as e:
            log_campaign_action("SheetsService", status="ERROR", error=str(e), message=f"Failed connecting to sheet '{self.spreadsheet_id}'")
            return False

    def _ensure_schema(self) -> None:
        """
        Auto-heals the sheet by verifying required headers and appending missing automatic system columns.
        """
        if not self.worksheet:
            return

        headers = self.worksheet.row_values(1)
        if not headers:
            headers = [COL_FIRST_NAME, COL_EMAIL, COL_VERIFIED, COL_RESPONSE_GOT]
            self.worksheet.update('A1', [headers])
            time.sleep(1)

        headers_existing_clean = [h.strip() for h in headers]
        missing_auto_cols = [col for col in AUTOMATIC_COLUMNS if col not in headers_existing_clean]

        if missing_auto_cols:
            start_col_idx = len(headers_existing_clean) + 1
            new_headers = headers_existing_clean + missing_auto_cols
            self.worksheet.update('A1', [new_headers])
            log_campaign_action("SheetsService", status="INFO", message=f"Appended missing columns: {missing_auto_cols}")
            headers_existing_clean = new_headers

        # Re-index headers: Column Name -> 1-based column index
        self.header_map = {h: idx + 1 for idx, h in enumerate(headers_existing_clean)}
        self._apply_column_aliases(self.header_map)

    def _apply_column_aliases(self, header_map: Dict[str, int]) -> None:
        """
        Lets a sheet use an alternate header name (e.g. "Name") in place of the
        canonical column name (e.g. "First Name") by pointing the canonical name
        at the same column index, without requiring the sheet to be renamed.
        """
        for canonical, aliases in COLUMN_ALIASES.items():
            if canonical in header_map:
                continue
            for alias in aliases:
                if alias in header_map:
                    header_map[canonical] = header_map[alias]
                    break


    def read_all_contacts(self) -> List[Dict[str, Any]]:
        """
        Reads all records from the Google Sheet.
        Returns a list of dicts, including '_row_number' (1-indexed row number).
        """
        if not self.worksheet:
            if not self.connect():
                return []

        try:
            start_time = time.time()
            all_values = self.worksheet.get_all_values()
            if not all_values or len(all_values) <= 1:
                return []

            headers = [h.strip() for h in all_values[0]]
            self.header_map = {h: idx + 1 for idx, h in enumerate(headers)}
            self._apply_column_aliases(self.header_map)

            records = []
            for row_idx, row_values in enumerate(all_values[1:], start=2):
                row_dict = {"_row_number": row_idx}
                for col_name, col_idx in self.header_map.items():
                    val = row_values[col_idx - 1] if (col_idx - 1) < len(row_values) else ""
                    row_dict[col_name] = val
                records.append(row_dict)

            # Normalize keys for backward compatibility
            for r in records:
                if "Email Sent Date" in r and COL_EMAIL_SENT_DATE not in r:
                    r[COL_EMAIL_SENT_DATE] = r["Email Sent Date"]
                if "Follow-up Sent Date" in r and COL_FOLLOWUP_SENT_DATE not in r:
                    r[COL_FOLLOWUP_SENT_DATE] = r["Follow-up Sent Date"]

            elapsed_ms = (time.time() - start_time) * 1000
            log_campaign_action("SheetsService", status="SUCCESS", execution_time_ms=elapsed_ms, message=f"Fetched {len(records)} contacts")
            return records
        except Exception as e:
            log_campaign_action("SheetsService", status="ERROR", error=str(e), message="Error reading sheet contacts")
            return []

    def ensure_column(self, col_name: str) -> int:
        """
        Ensures a column exists in the sheet header row, creating it (appended at the
        end) if missing. Used for dynamically-named resend columns (e.g. "Email Sent
        Date & Time 2") that aren't part of the fixed AUTOMATIC_COLUMNS list.
        Returns the column's 1-based index.
        """
        if col_name in self.header_map:
            return self.header_map[col_name]

        if not self.worksheet:
            if not self.connect():
                raise RuntimeError("Cannot connect to worksheet to add column")

        next_idx = max(self.header_map.values(), default=0) + 1
        self.worksheet.update_cell(1, next_idx, col_name)
        self.header_map[col_name] = next_idx
        log_campaign_action("SheetsService", status="INFO", message=f"Added new column '{col_name}' at index {next_idx}")
        return next_idx

    def queue_row_update(self, row_number: int, updates: Dict[str, Any]) -> None:
        """
        Queues cell updates for application-owned columns.
        Explicitly prevents overwriting Response Got or unmapped user columns.
        """
        for col_name, val in updates.items():
            if col_name in USER_PROTECTED_COLUMNS:
                continue
            if col_name in self.header_map:
                col_idx = self.header_map[col_name]
                str_val = str(val) if val is not None else ""
                self.update_queue.append(Cell(row=row_number, col=col_idx, value=str_val))


    def flush_updates(self) -> bool:
        """
        Flushes all queued cell updates in a single batch request to minimize API usage.
        """
        if not self.update_queue:
            return True

        if not self.worksheet:
            if not self.connect():
                return False

        try:
            start_time = time.time()
            count = len(self.update_queue)
            self.worksheet.update_cells(self.update_queue)
            self.update_queue.clear()
            elapsed_ms = (time.time() - start_time) * 1000
            log_campaign_action("SheetsService", status="SUCCESS", execution_time_ms=elapsed_ms, message=f"Flushed batch update of {count} cells")
            return True
        except Exception as e:
            log_campaign_action("SheetsService", status="ERROR", error=str(e), message="Error executing batch cell update")
            return False

    def update_row_immediately(self, row_number: int, updates: Dict[str, Any]) -> bool:
        """
        Queues and immediately flushes updates for a single row.
        """
        self.queue_row_update(row_number, updates)
        return self.flush_updates()

    def get_connection_status(self) -> Dict[str, Any]:
        """Returns health indicator dict for Google Sheets connection."""
        if not self.spreadsheet_id:
            return {"status": "No Sheet Configured", "color": "yellow"}

        try:
            if not self.worksheet:
                connected = self.connect()
            else:
                connected = True

            if connected:
                return {
                    "status": "Connected",
                    "color": "green",
                    "title": self.spreadsheet.title if self.spreadsheet else "Sheet",
                    "sheet_id": self.spreadsheet_id,
                }
            else:
                return {"status": "Connection Error", "color": "red", "sheet_id": self.spreadsheet_id}
        except Exception as e:
            return {"status": "Error", "color": "red", "error": str(e)}
