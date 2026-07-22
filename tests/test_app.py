"""
tests/test_app.py - Unit Tests for Automated Email Campaign Manager
"""
import unittest
from config import extract_spreadsheet_id, ConfigManager, Campaign
from utils.validator import validate_email_address, evaluate_contact_row
from services.email_service import render_template_string


class TestEmailCampaignManager(unittest.TestCase):

    def test_spreadsheet_id_extraction(self):
        url = "https://docs.google.com/spreadsheets/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms/edit#gid=0"
        extracted = extract_spreadsheet_id(url)
        self.assertEqual(extracted, "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms")

        raw_id = "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms"
        self.assertEqual(extract_spreadsheet_id(raw_id), raw_id)

    def test_email_validation(self):
        valid, norm = validate_email_address("john.doe@example.com")
        self.assertTrue(valid)
        self.assertEqual(norm.lower(), "john.doe@example.com")

        invalid, err = validate_email_address("invalid-email-format")
        self.assertFalse(invalid)

    def test_contact_row_evaluation(self):
        seen = set()
        row_valid = {
            "First Name": "Alice",
            "Email": "alice@example.com",
            "Verified": "Yes",
        }
        res = evaluate_contact_row(row_valid, seen)
        self.assertTrue(res["can_send"])

        # Test duplicate
        res_dup = evaluate_contact_row(row_valid, seen)
        self.assertFalse(res_dup["can_send"])
        self.assertTrue(res_dup["is_duplicate"])

    def test_jinja2_rendering(self):
        tmpl = "Hello {{first_name}}, welcome to {{company}}!"
        context = {"first_name": "Bob", "company": "Acme Corp"}
        rendered = render_template_string(tmpl, context)
        self.assertEqual(rendered, "Hello Bob, welcome to Acme Corp!")

    def test_db_service(self):
        from services.db_service import DBService
        db = DBService("data/test_contacts.db")
        records = [
            {"First Name": "Alice", "Email": "alice@test.com", "Verified": "Yes"},
            {"First Name": "Bob", "Email": "bob@test.com", "Verified": "Yes"},
        ]
        inserted = db.import_contacts("test_camp", records, overwrite=True)
        self.assertEqual(inserted, 2)
        
        fetched = db.read_all_contacts("test_camp")
        self.assertEqual(len(fetched), 2)
        self.assertEqual(fetched[0]["Email"], "alice@test.com")

        # Clean up
        import gc
        del db
        gc.collect()
        import os
        if os.path.exists("data/test_contacts.db"):
            try:
                os.remove("data/test_contacts.db")
            except Exception:
                pass

    def test_db_service_reset(self):
        from services.db_service import DBService
        db = DBService("data/test_contacts_reset.db")
        records = [
            {
                "First Name": "Alice",
                "Email": "alice@test.com",
                "Verified": "Yes",
                "Status": "Sent",
                "Email Sent Date & Time": "2026-07-22 14:00:00",
                "Attempt Count": "1",
            }
        ]
        db.import_contacts("test_camp", records, overwrite=True)
        
        # Verify it imported Sent status
        fetched = db.read_all_contacts("test_camp")
        self.assertEqual(fetched[0]["Status"], "Sent")
        self.assertEqual(fetched[0]["Email Sent Date & Time"], "2026-07-22 14:00:00")
        self.assertEqual(fetched[0]["Attempt Count"], "1")
        
        # Reset contacts
        db.reset_campaign_contacts("test_camp")
        
        # Verify columns are reset
        fetched_after = db.read_all_contacts("test_camp")
        self.assertEqual(fetched_after[0]["Status"], "Pending")
        self.assertEqual(fetched_after[0]["Email Sent Date & Time"], "")
        self.assertEqual(fetched_after[0]["Attempt Count"], "0")
        
        # Clean up
        import gc
        del db
        gc.collect()
        import os
        if os.path.exists("data/test_contacts_reset.db"):
            try:
                os.remove("data/test_contacts_reset.db")
            except Exception:
                pass


if __name__ == "__main__":
    unittest.main()
