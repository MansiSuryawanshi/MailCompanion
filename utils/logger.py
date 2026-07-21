"""
utils/logger.py - Application & Campaign Action Logger
"""
import csv
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional
import pandas as pd

from constants import LOG_FILE, LOGS_DIR


class MemoryLogHandler(logging.Handler):
    """In-memory log storage handler for UI display and CSV export."""
    def __init__(self, capacity: int = 1000):
        super().__init__()
        self.capacity = capacity
        self.records: List[Dict[str, Any]] = []

    def emit(self, record: logging.LogRecord):
        log_entry = {
            "timestamp": datetime.fromtimestamp(record.created).strftime("%Y-%m-%d %H:%M:%S"),
            "level": record.levelname,
            "message": record.getMessage(),
            "recipient": getattr(record, "recipient", "-"),
            "action": getattr(record, "action", record.funcName),
            "execution_time_ms": getattr(record, "execution_time_ms", 0),
            "retry_count": getattr(record, "retry_count", 0),
            "status": getattr(record, "status", record.levelname),
            "error": getattr(record, "error", ""),
        }
        self.records.insert(0, log_entry)  # Newest first
        if len(self.records) > self.capacity:
            self.records.pop()


_memory_handler = MemoryLogHandler()


def setup_logger() -> logging.Logger:
    """Configures root application logger."""
    os.makedirs(LOGS_DIR, exist_ok=True)
    logger = logging.getLogger("EmailCampaignManager")
    logger.setLevel(logging.INFO)

    if not logger.handlers:
        # File handler
        file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
        file_formatter = logging.Formatter(
            "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s"
        )
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

        # Memory handler for UI
        logger.addHandler(_memory_handler)

    return logger


logger = setup_logger()


def log_campaign_action(
    action: str,
    recipient: str = "-",
    status: str = "INFO",
    execution_time_ms: float = 0.0,
    retry_count: int = 0,
    error: str = "",
    message: str = "",
) -> None:
    """Helper to record structured campaign events."""
    extra = {
        "action": action,
        "recipient": recipient,
        "status": status,
        "execution_time_ms": round(execution_time_ms, 2),
        "retry_count": retry_count,
        "error": error,
    }
    msg = message if message else f"{action} for {recipient} -> {status}"
    if status in ("FAILED", "ERROR"):
        logger.error(msg, extra=extra)
    elif status == "WARNING":
        logger.warning(msg, extra=extra)
    else:
        logger.info(msg, extra=extra)


def get_memory_logs() -> List[Dict[str, Any]]:
    """Get all in-memory logged events."""
    return _memory_handler.records


def get_logs_dataframe() -> pd.DataFrame:
    """Return in-memory logs as a Pandas DataFrame."""
    records = get_memory_logs()
    if not records:
        return pd.DataFrame(columns=[
            "timestamp", "level", "action", "recipient", 
            "status", "execution_time_ms", "retry_count", "message", "error"
        ])
    return pd.DataFrame(records)


def export_logs_to_csv() -> str:
    """Exports logs to a CSV string."""
    df = get_logs_dataframe()
    return df.to_csv(index=False)
