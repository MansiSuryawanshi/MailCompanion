"""
utils/validator.py - Strict Email & Contact Row Validation Module
"""
import re
from typing import Any, Dict, List, Tuple
from email_validator import validate_email, EmailNotValidError

from constants import (
    COL_EMAIL,
    COL_FIRST_NAME,
    COL_VERIFIED,
    VERIFICATION_TRUTHS,
)

def is_truthy(value: Any) -> bool:
    """Helper to check if a value represents boolean True in various string/int representations."""
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value == 1
    val_str = str(value).strip().lower()
    return val_str in VERIFICATION_TRUTHS


def validate_email_address(email_str: str) -> Tuple[bool, str]:
    """
    Validates an email address using RFC-compliant email-validator package.
    Returns (is_valid: bool, error_message: str).
    """
    if not email_str or not str(email_str).strip():
        return False, "Missing email address"
    
    clean_email = str(email_str).strip()
    try:
        # validate_email checks syntax and domain structure
        valid_info = validate_email(clean_email, check_deliverability=False)
        # Check normalized email
        return True, valid_info.normalized
    except EmailNotValidError as e:
        return False, str(e)
    except Exception as e:
        return False, f"Invalid email format: {str(e)}"


def evaluate_contact_row(
    row: Dict[str, Any], 
    seen_emails: set
) -> Dict[str, Any]:
    """
    Evaluates a contact row against verification and sending rules.
    Returns evaluation result dictionary:
      - valid_email (bool)
      - is_verified (bool)
      - is_duplicate (bool)
      - missing_name (bool)
      - can_send (bool)
      - reason (str)
    """
    first_name = str(row.get(COL_FIRST_NAME, "") or "").strip()
    email_raw = str(row.get(COL_EMAIL, "") or "").strip()
    verified_raw = row.get(COL_VERIFIED, "")

    missing_name = not bool(first_name)
    is_verified = is_truthy(verified_raw)
    
    # 1. Email Presence & Format
    valid_email, norm_or_err = validate_email_address(email_raw)
    if not valid_email:
        return {
            "valid_email": False,
            "is_verified": is_verified,
            "is_duplicate": False,
            "missing_name": missing_name,
            "can_send": False,
            "reason": f"Invalid Email: {norm_or_err}",
        }

    normalized_email = norm_or_err.lower()

    # 2. Duplicate Check
    is_duplicate = normalized_email in seen_emails
    seen_emails.add(normalized_email)

    if is_duplicate:
        return {
            "valid_email": True,
            "is_verified": is_verified,
            "is_duplicate": True,
            "missing_name": missing_name,
            "can_send": False,
            "reason": "Duplicate email in contact list",
        }

    # 3. Missing First Name
    if missing_name:
        return {
            "valid_email": True,
            "is_verified": is_verified,
            "is_duplicate": False,
            "missing_name": True,
            "can_send": False,
            "reason": "Missing first name",
        }

    # 4. Verification Check
    if not is_verified:
        return {
            "valid_email": True,
            "is_verified": False,
            "is_duplicate": False,
            "missing_name": False,
            "can_send": False,
            "reason": "Not verified",
        }

    # All checks passed
    return {
        "valid_email": True,
        "is_verified": True,
        "is_duplicate": False,
        "missing_name": False,
        "can_send": True,
        "reason": "Eligible for sending",
    }
