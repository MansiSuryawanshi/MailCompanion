"""
ui/settings.py - Global Application Settings & Backup Manager Page
"""
import json
import streamlit as st
from config import ConfigManager, extract_spreadsheet_id
from services.auth_service import AuthService
from scheduler import global_scheduler


def render_settings(config_manager: ConfigManager, auth_service: AuthService):
    st.title("⚙️ Global Settings & Backup")
    st.caption("Configure global application parameters, Google OAuth connection, scheduler, and backup settings JSON.")

    active_campaign = config_manager.get_active_campaign()

    tab_global, tab_oauth, tab_scheduler, tab_backup = st.tabs([
        "⚙️ Global Preferences", "🔐 Google OAuth", "⏰ Scheduler", "📦 Backup & Restore"
    ])

    with tab_global:
        with st.form("global_settings_form"):
            st.subheader("Sender Identity")
            sender_name = st.text_input("Sender Name", value=config_manager.settings.get("sender_name", "Mansi"))
            email_sig = st.text_area("Email HTML Signature", value=config_manager.settings.get("email_signature", ""), height=100)

            st.subheader("Sending & Rate Limits")
            col1, col2 = st.columns(2)
            with col1:
                min_delay = st.number_input("Global Min Send Delay (sec)", value=float(config_manager.settings.get("min_send_delay", 3.0)), min_value=1.0, max_value=60.0)
                followup_days = st.number_input("Global Follow-up Delay (days)", value=int(config_manager.settings.get("followup_days", 3)), min_value=1, max_value=30)
                batch_size = st.number_input("Google Sheet Batch Flush Size (rows)", value=int(config_manager.settings.get("batch_size", 20)), min_value=1, max_value=100)
            with col2:
                max_delay = st.number_input("Global Max Send Delay (sec)", value=float(config_manager.settings.get("max_send_delay", 7.0)), min_value=1.0, max_value=60.0)
                daily_limit = st.number_input("Global Daily Limit", value=int(config_manager.settings.get("daily_limit", 100)), min_value=1, max_value=5000)
                timezone = st.text_input("Timezone", value=config_manager.settings.get("timezone", "UTC"))

            save_btn = st.form_submit_button("Save Global Settings", type="primary")
            if save_btn:
                config_manager.settings["sender_name"] = sender_name
                config_manager.settings["email_signature"] = email_sig
                config_manager.settings["min_send_delay"] = min_delay
                config_manager.settings["max_send_delay"] = max_delay
                config_manager.settings["followup_days"] = followup_days
                config_manager.settings["batch_size"] = batch_size
                config_manager.settings["daily_limit"] = daily_limit
                config_manager.settings["timezone"] = timezone
                config_manager.save_settings()
                st.success("Global preferences saved successfully!")

    with tab_oauth:
        st.subheader("Google OAuth 2.0 Connection Health")
        auth_status = auth_service.get_auth_status()

        st.write(f"**Status:** `{auth_status['status']}`")
        st.write(f"**Account Email:** `{auth_status.get('email', 'N/A')}`")
        st.write(f"**Client Secret File Present:** `{auth_status['client_secret_present']}`")
        st.write(f"**Token Valid:** `{auth_status['token_valid']}`")

        if st.button("🔑 Reconnect / Authenticate Google Account", type="primary"):
            try:
                auth_service.authenticate_interactive()
                st.success("Authenticated successfully!")
                st.rerun()
            except Exception as e:
                st.error(f"Authentication error: {e}")

    with tab_scheduler:
        st.subheader("APScheduler Automation Control")
        sched_info = global_scheduler.get_status()

        st.write(f"**Scheduler Status:** `{sched_info['status']}`")
        st.write(f"**Next Run Time:** `{sched_info['next_run']}`")

        cron_time = st.text_input("Daily Execution Time (HH:MM 24hr format):", value=config_manager.settings.get("scheduler_time", "10:00"))

        col_sch1, col_sch2 = st.columns(2)
        with col_sch1:
            if st.button("▶️ Start Background Scheduler", type="primary", use_container_width=True):
                global_scheduler.start(cron_time)
                config_manager.settings["scheduler_enabled"] = True
                config_manager.settings["scheduler_time"] = cron_time
                config_manager.save_settings()
                st.success(f"Scheduler enabled for daily run at {cron_time}")
                st.rerun()

        with col_sch2:
            if st.button("⏹️ Stop Background Scheduler", use_container_width=True):
                global_scheduler.stop()
                config_manager.settings["scheduler_enabled"] = False
                config_manager.save_settings()
                st.info("Scheduler disabled.")
                st.rerun()

    with tab_backup:
        st.subheader("Settings Backup & Restore")
        st.write("Export or import all campaigns and settings as a JSON backup.")

        export_data = config_manager.export_all_config()
        json_str = json.dumps(export_data, indent=4)

        st.download_button(
            label="📥 Export Settings Backup (JSON)",
            data=json_str,
            file_name="email_campaign_settings_backup.json",
            mime="application/json",
            use_container_width=True,
        )

        st.divider()
        uploaded_file = st.file_uploader("Upload Settings Backup JSON to Restore:", type=["json"])
        if uploaded_file is not None:
            try:
                data = json.load(uploaded_file)
                if config_manager.import_all_config(data):
                    st.success("Imported configuration successfully!")
                    st.rerun()
                else:
                    st.error("Failed to import configuration file.")
            except Exception as e:
                st.error(f"Invalid JSON file: {e}")
