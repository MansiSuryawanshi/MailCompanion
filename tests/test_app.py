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

    def test_db_service_verification_mapping(self):
        from services.db_service import DBService
        db = DBService("data/test_contacts_ver.db")
        records = [
            {"Name": "Sai", "email": "sai@test.com", "Email Verified": "unverified"},
            {"First Name": "Mansi", "Email": "mansi@test.com", "Email Verified": "verified"},
            {"First Name": "Ojas", "Email": "ojas@test.com", "is_verified": "true"},
            {"First Name": "Tushar", "Email": "tushar@test.com"}
        ]
        db.import_contacts("test_camp", records, overwrite=True)
        fetched = db.read_all_contacts("test_camp")
        
        self.assertEqual(len(fetched), 4)
        
        # Check that "sai@test.com" has verified = "No"
        sai_contact = next(c for c in fetched if c["Email"] == "sai@test.com")
        self.assertEqual(sai_contact["Verified"], "No")
        # Ensure 'Email Verified' and 'Name' are NOT in extra_json
        import json
        db_conn = db._get_connection()
        row = db_conn.execute("SELECT extra_json FROM contacts WHERE email = 'sai@test.com'").fetchone()
        extra = json.loads(row["extra_json"])
        self.assertNotIn("Email Verified", extra)
        self.assertNotIn("Name", extra)
        
        # Check that "mansi@test.com" has verified = "Yes"
        mansi_contact = next(c for c in fetched if c["Email"] == "mansi@test.com")
        self.assertEqual(mansi_contact["Verified"], "Yes")
        
        # Check that "ojas@test.com" has verified = "Yes"
        ojas_contact = next(c for c in fetched if c["Email"] == "ojas@test.com")
        self.assertEqual(ojas_contact["Verified"], "Yes")
        
        # Check that "tushar@test.com" defaulted to "Yes"
        tushar_contact = next(c for c in fetched if c["Email"] == "tushar@test.com")
        self.assertEqual(tushar_contact["Verified"], "Yes")

        # Clean up
        import gc
        del db
        gc.collect()
        import os
        if os.path.exists("data/test_contacts_ver.db"):
            try:
                os.remove("data/test_contacts_ver.db")
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

    def test_db_service_sync_non_overwrite(self):
        from services.db_service import DBService
        db = DBService("data/test_contacts_sync.db")
        
        # 1. Initial records
        initial_records = [
            {
                "First Name": "Alice",
                "Email": "alice@test.com",
                "Verified": "Yes",
                "Status": "Sent",
                "Email Sent Date & Time": "2026-07-22 14:00:00",
            }
        ]
        db.import_contacts("test_camp", initial_records, overwrite=True)
        
        # 2. Sync updated first name, and a new pending contact (overwrite=False)
        sync_records = [
            {
                "First Name": "Alice Updated",
                "Email": "alice@test.com",
                "Verified": "Yes",
                "Status": "",
            },
            {
                "First Name": "Bob",
                "Email": "bob@test.com",
                "Verified": "Yes",
                "Status": "Pending",
            }
        ]
        db.import_contacts("test_camp", sync_records, overwrite=False)
        
        # 3. Verify Alice's status/sent date is preserved, first name is updated
        # Verify Bob is added as Pending
        fetched = db.read_all_contacts("test_camp")
        self.assertEqual(len(fetched), 2)
        
        alice = next(c for c in fetched if c["Email"] == "alice@test.com")
        bob = next(c for c in fetched if c["Email"] == "bob@test.com")
        
        self.assertEqual(alice["First Name"], "Alice Updated")
        self.assertEqual(alice["Status"], "Sent")
        self.assertEqual(alice["Email Sent Date & Time"], "2026-07-22 14:00:00")
        
        self.assertEqual(bob["First Name"], "Bob")
        self.assertEqual(bob["Status"], "Pending")
        
        # Clean up
        import gc
        del db
        gc.collect()
        import os
        if os.path.exists("data/test_contacts_sync.db"):
            try:
                os.remove("data/test_contacts_sync.db")
            except Exception:
                pass

    def test_verified_status_defaulting(self):
        from services.db_service import DBService
        db = DBService("data/test_contacts_verified_default.db")

        records = [
            # 1. Verification column missing entirely -> defaults to "Yes"
            {
                "First Name": "Alice",
                "Email": "alice@test.com",
            },
            # 2. Verification column present but blank/empty -> resolves to "No"
            {
                "First Name": "Bob",
                "Email": "bob@test.com",
                "Verified": "",
            },
            # 3. Verification column present but None -> resolves to "No"
            {
                "First Name": "Charlie",
                "Email": "charlie@test.com",
                "Verified": None,
            },
            # 4. Verification column present and set to "No" -> resolves to "No"
            {
                "First Name": "David",
                "Email": "david@test.com",
                "Verified": "No",
            },
            # 5. Verification column present and set to "Yes" -> resolves to "Yes"
            {
                "First Name": "Eve",
                "Email": "eve@test.com",
                "Verified": "Yes",
            }
        ]

        db.import_contacts("test_camp", records, overwrite=True)

        fetched = db.read_all_contacts("test_camp")
        self.assertEqual(len(fetched), 5)

        alice = next(c for c in fetched if c["Email"] == "alice@test.com")
        bob = next(c for c in fetched if c["Email"] == "bob@test.com")
        charlie = next(c for c in fetched if c["Email"] == "charlie@test.com")
        david = next(c for c in fetched if c["Email"] == "david@test.com")
        eve = next(c for c in fetched if c["Email"] == "eve@test.com")

        self.assertEqual(alice["Verified"], "Yes")
        self.assertEqual(bob["Verified"], "No")
        self.assertEqual(charlie["Verified"], "No")
        self.assertEqual(david["Verified"], "No")
        self.assertEqual(eve["Verified"], "Yes")

        # Clean up
        import gc
        del db
        gc.collect()
        import os
        if os.path.exists("data/test_contacts_verified_default.db"):
            try:
                os.remove("data/test_contacts_verified_default.db")
            except Exception:
                pass

    def test_custom_scheduler_logic(self):
        from scheduler import CampaignScheduler
        from datetime import datetime
        
        sched = CampaignScheduler()
        
        # Test daily mode
        settings_daily = {"scheduler_mode": "daily"}
        t1 = datetime(2026, 7, 23, 10, 0, 0)
        self.assertTrue(sched.is_scheduled_date(t1, settings_daily))
        
        # Test weekdays mode
        settings_weekdays = {
            "scheduler_mode": "weekdays",
            "scheduler_weekdays": ["Monday", "Wednesday", "Friday"]
        }
        mon = datetime(2026, 7, 20, 10, 0, 0) # Monday
        tue = datetime(2026, 7, 21, 10, 0, 0) # Tuesday
        self.assertTrue(sched.is_scheduled_date(mon, settings_weekdays))
        self.assertFalse(sched.is_scheduled_date(tue, settings_weekdays))
        
        # Test specific dates mode
        settings_dates = {
            "scheduler_mode": "dates",
            "scheduler_dates": ["2026-07-24", "2026-07-26"]
        }
        self.assertTrue(sched.is_scheduled_date(datetime(2026, 7, 24, 12, 0, 0), settings_dates))
        self.assertFalse(sched.is_scheduled_date(datetime(2026, 7, 25, 12, 0, 0), settings_dates))
        
        # Test interval mode
        settings_interval = {
            "scheduler_mode": "interval",
            "scheduler_interval_gap": 2, # every 3 days
            "scheduler_interval_start": "2026-07-20"
        }
        self.assertTrue(sched.is_scheduled_date(datetime(2026, 7, 20, 10, 0, 0), settings_interval)) # day 0
        self.assertFalse(sched.is_scheduled_date(datetime(2026, 7, 21, 10, 0, 0), settings_interval)) # day 1
        self.assertFalse(sched.is_scheduled_date(datetime(2026, 7, 22, 10, 0, 0), settings_interval)) # day 2
        self.assertTrue(sched.is_scheduled_date(datetime(2026, 7, 23, 10, 0, 0), settings_interval)) # day 3
        
        # Test calculate_next_run
        settings_next = {
            "scheduler_enabled": True,
            "scheduler_time": "10:00",
            "scheduler_mode": "weekdays",
            "scheduler_weekdays": ["Monday", "Wednesday"]
        }
        # 2026-07-20 is Monday, 2026-07-19 is Sunday
        start_sun = datetime(2026, 7, 19, 15, 0, 0)
        next_run = sched.calculate_next_run(start_sun, settings_next)
        self.assertIsNotNone(next_run)
        # Should run on Monday 2026-07-20 at 10:00
        self.assertEqual(next_run.strftime("%Y-%m-%d %H:%M:%S"), "2026-07-20 10:00:00")


if __name__ == "__main__":
    unittest.main()
