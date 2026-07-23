"""
ui/settings.py - Global Application Settings & Backup Manager Page
"""
import json
from datetime import datetime, timedelta
import streamlit as st
from config import ConfigManager, extract_spreadsheet_id
from services.auth_service import AuthService
from scheduler import global_scheduler


def render_settings(config_manager: ConfigManager, auth_service: AuthService):
    st.title("⚙️ Settings & Connections")
    st.caption("Set your default details, connect to Google, schedule automated sends, and backup settings.")

    active_campaign = config_manager.get_active_campaign()

    tab_global, tab_oauth, tab_scheduler, tab_backup = st.tabs([
        "⚙️ Default Preferences", "🔐 Google Account", "⏰ Automatic Scheduling", "📦 Import & Export Backup"
    ])

    with tab_global:
        with st.form("global_settings_form"):
            st.subheader("Your Identity (Default)")
            sender_name = st.text_input("Your Name", value=config_manager.settings.get("sender_name", "Mansi"))
            email_sig = st.text_area("Your Email Signature (HTML template)", value=config_manager.settings.get("email_signature", ""), height=100)

            st.subheader("Limits & Speeds")
            col1, col2 = st.columns(2)
            with col1:
                min_delay = st.number_input("Min gap between emails (seconds)", value=float(config_manager.settings.get("min_send_delay", 3.0)), min_value=1.0, max_value=60.0)
                followup_days = st.number_input("Default wait before follow-ups (days)", value=int(config_manager.settings.get("followup_days", 3)), min_value=1, max_value=30)
                batch_size = st.number_input("Save progress to sheet every N rows", value=int(config_manager.settings.get("batch_size", 20)), min_value=1, max_value=100)
            with col2:
                max_delay = st.number_input("Max gap between emails (seconds)", value=float(config_manager.settings.get("max_send_delay", 7.0)), min_value=1.0, max_value=60.0)
                daily_limit = st.number_input("Max emails sent per day", value=int(config_manager.settings.get("daily_limit", 100)), min_value=1, max_value=5000)
                timezone = st.text_input("Your Time Zone", value=config_manager.settings.get("timezone", "UTC"))

            save_btn = st.form_submit_button("Save Default Preferences", type="primary")
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
                st.success("Default preferences saved successfully!")

    with tab_oauth:
        st.subheader("🔐 Connect Google Accounts")
        st.caption("You can link multiple Google accounts and choose the active account to send campaigns from.")
        
        # Connect New Account Section
        col_btn, col_info = st.columns([1, 2])
        with col_btn:
            if st.button("🔑 Connect a Google Account", type="primary", use_container_width=True):
                try:
                    auth_service.authenticate_interactive()
                    st.success("New account connected successfully!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Authentication error: {e}")
        with col_info:
            st.info("Click the button to open a browser window and log in with your Google account. Ensure you have authorized the necessary permissions.")

        st.divider()

        # Connected Accounts List
        st.subheader("👥 Connected Google Accounts")
        connected_accounts = auth_service.get_connected_accounts()

        if connected_accounts:
            emails = [acc["email"] for acc in connected_accounts]
            active_email = config_manager.settings.get("active_sender_email", "")
            
            # Ensure the active_email is valid/still connected
            if active_email not in emails and emails:
                active_email = emails[0]
                config_manager.settings["active_sender_email"] = active_email
                config_manager.save_settings()
                # copy token
                import shutil
                shutil.copy(f"credentials/token_{active_email}.json", "credentials/token.json")

            # Selection for Global Active Account
            selected_active = st.selectbox(
                "Select Global Default Sender Account:",
                options=emails,
                index=emails.index(active_email) if active_email in emails else 0
            )

            if selected_active != active_email:
                config_manager.settings["active_sender_email"] = selected_active
                config_manager.save_settings()
                # copy token_<email>.json to token.json
                import shutil
                shutil.copy(f"credentials/token_{selected_active}.json", "credentials/token.json")
                st.success(f"Switched default account to '{selected_active}'")
                st.rerun()

            st.write("") # spacing
            # Display accounts detail list
            for acc in connected_accounts:
                c_email = acc["email"]
                c_valid = acc["valid"]
                is_active = (c_email == active_email)

                # Visual design for each account row using a clean layout
                col_acc_info, col_acc_act = st.columns([3, 1])
                with col_acc_info:
                    status_indicator = "🟢 Active Default" if is_active else ("🔵 Connected" if c_valid else "🔴 Needs Re-Auth")
                    st.markdown(f"**{c_email}** ({status_indicator})")
                with col_acc_act:
                    if st.button("🗑️ Disconnect", key=f"disconnect_{c_email}", use_container_width=True):
                        if auth_service.disconnect_account(c_email):
                            # Reset active sender if it was deleted
                            if active_email == c_email:
                                config_manager.settings["active_sender_email"] = ""
                                config_manager.save_settings()
                            st.success(f"Disconnected {c_email}")
                            st.rerun()
                        else:
                            st.error("Failed to disconnect account.")
                st.markdown("<hr style='margin: 0.5rem 0; opacity: 0.3;'>", unsafe_allow_html=True)
        else:
            st.warning("No Google accounts connected yet. Please connect an account above.")

    with tab_scheduler:
        st.subheader("⏰ Auto-Send Schedule Settings")
        sched_info = global_scheduler.get_status()

        col_st1, col_st2 = st.columns(2)
        with col_st1:
            st.write(f"**Automation Active:** `{sched_info['status']}`")
        with col_st2:
            st.write(f"**Next Automated Run scheduled at:** `{sched_info['next_run']}`")

        st.divider()

        # Inputs for schedule settings
        cron_time = st.text_input("Daily run time (e.g. 10:00 for 10 AM):", value=config_manager.settings.get("scheduler_time", "10:00"))
        
        mode_options = {
            "daily": "📅 Every single day",
            "weekdays": "🗓️ On specific days of the week",
            "dates": "📅 On specific custom calendar dates",
            "interval": "⏱️ Run after a gap of N days"
        }
        
        current_mode = config_manager.settings.get("scheduler_mode", "daily")
        selected_mode = st.selectbox(
            "Schedule Mode:",
            options=list(mode_options.keys()),
            format_func=lambda x: mode_options[x],
            index=list(mode_options.keys()).index(current_mode) if current_mode in mode_options else 0
        )
        
        # Save mode changes
        if selected_mode != current_mode:
            config_manager.settings["scheduler_mode"] = selected_mode
            config_manager.save_settings()
            st.rerun()

        # Render conditional UI based on selected mode
        if selected_mode == "weekdays":
            weekdays_options = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
            current_weekdays = config_manager.settings.get("scheduler_weekdays", weekdays_options)
            selected_weekdays = st.multiselect(
                "Select days:",
                options=weekdays_options,
                default=current_weekdays
            )
            if selected_weekdays != current_weekdays:
                config_manager.settings["scheduler_weekdays"] = selected_weekdays
                config_manager.save_settings()
                st.rerun()

        elif selected_mode == "dates":
            st.write("##### Add specific run dates:")
            col_d1, col_d2 = st.columns([2, 1])
            with col_d1:
                selected_date = st.date_input("Pick a calendar date:")
            with col_d2:
                st.write("") # spacing
                st.write("") # spacing
                if st.button("➕ Add Date", use_container_width=True):
                    date_str = selected_date.strftime("%Y-%m-%d")
                    current_dates = config_manager.settings.get("scheduler_dates", [])
                    if date_str not in current_dates:
                        current_dates.append(date_str)
                        config_manager.settings["scheduler_dates"] = current_dates
                        config_manager.save_settings()
                        st.success(f"Added {date_str} to schedule.")
                        st.rerun()
            
            # Show list of dates with option to remove
            current_dates = config_manager.settings.get("scheduler_dates", [])
            if current_dates:
                current_dates = sorted(current_dates)
                st.write("##### Scheduled dates:")
                updated_dates = st.multiselect(
                    "Dates currently scheduled (Click X to remove):",
                    options=current_dates,
                    default=current_dates
                )
                if updated_dates != current_dates:
                    config_manager.settings["scheduler_dates"] = updated_dates
                    config_manager.save_settings()
                    st.rerun()
            else:
                st.info("No specific dates added yet. Please select a date above and click 'Add Date'.")

        elif selected_mode == "interval":
            current_gap = int(config_manager.settings.get("scheduler_interval_gap", 1))
            current_start_str = config_manager.settings.get("scheduler_interval_start", datetime.now().strftime("%Y-%m-%d"))
            try:
                current_start = datetime.strptime(current_start_str, "%Y-%m-%d").date()
            except ValueError:
                current_start = datetime.now().date()

            col_int1, col_int2 = st.columns(2)
            with col_int1:
                gap = st.number_input(
                    "Wait this many days between runs:",
                    min_value=1,
                    max_value=365,
                    value=current_gap,
                    help="For example: waiting 1 day means running every 2nd day. Waiting 2 days means running every 3rd day."
                )
            with col_int2:
                start_date = st.date_input("Starting date:", value=current_start)

            if gap != current_gap or start_date.strftime("%Y-%m-%d") != current_start_str:
                config_manager.settings["scheduler_interval_gap"] = int(gap)
                config_manager.settings["scheduler_interval_start"] = start_date.strftime("%Y-%m-%d")
                config_manager.save_settings()
                st.rerun()

            # Preview next runs
            st.write("##### 📅 Preview of Next 3 Run Dates")
            preview_runs = []
            test_date = datetime.combine(start_date, datetime.min.time())
            for i in range(30):
                diff_days = (test_date.date() - start_date).days
                if diff_days >= 0 and diff_days % (gap + 1) == 0:
                    preview_runs.append(test_date.strftime("%Y-%m-%d (%A)"))
                    if len(preview_runs) >= 3:
                        break
                test_date += timedelta(days=1)
            
            if preview_runs:
                st.write("The next 3 scheduled runs will happen on:")
                for run in preview_runs:
                    st.write(f"- `{run}` at `{cron_time}`")

        st.divider()

        # Action Buttons
        col_sch1, col_sch2 = st.columns(2)
        with col_sch1:
            if st.button("▶️ Save & Turn On Automation", type="primary", use_container_width=True):
                # Update time in config
                config_manager.settings["scheduler_time"] = cron_time
                config_manager.settings["scheduler_enabled"] = True
                config_manager.save_settings()
                
                # Start / Restart scheduler
                global_scheduler.start(cron_time)
                st.success(f"Schedule settings saved and automated sending is active!")
                st.rerun()

        with col_sch2:
            if st.button("⏹️ Turn Off Automation", use_container_width=True):
                global_scheduler.stop()
                config_manager.settings["scheduler_enabled"] = False
                config_manager.save_settings()
                st.info("Automated sending turned off.")
                st.rerun()

    with tab_backup:
        st.subheader("Backup & Restore Everything")
        st.write("Save all your campaigns, settings, and templates to a file, or upload a previously saved file.")

        export_data = config_manager.export_all_config()
        json_str = json.dumps(export_data, indent=4)

        st.download_button(
            label="📥 Save All Data to a Backup File",
            data=json_str,
            file_name="email_campaign_settings_backup.json",
            mime="application/json",
            use_container_width=True,
        )

        st.divider()
        uploaded_file = st.file_uploader("Choose a backup file to restore your settings:", type=["json"])
        if uploaded_file is not None:
            try:
                data = json.load(uploaded_file)
                if config_manager.import_all_config(data):
                    st.success("Restored settings and campaigns successfully!")
                    st.rerun()
                else:
                    st.error("Failed to restore settings from this file.")
            except Exception as e:
                st.error(f"Invalid JSON file: {e}")
