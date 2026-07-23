"""
ui/dashboard.py - Dashboard Overview Page
"""
import streamlit as st
import pandas as pd
from datetime import datetime

from config import ConfigManager
from constants import (
    COL_FIRST_NAME,
    COL_EMAIL,
    COL_EMAIL_SENT_DATE,
    COL_FOLLOWUP_SENT_DATE,
    COL_RESPONSE_GOT,
    COL_STATUS,
    COL_VERIFIED,
    CampaignStatus,
    SendMode,
)
from services.auth_service import AuthService
from services.email_service import EmailService
from services.followup_service import FollowupService
from services.gmail_provider import GmailProvider
from services.sheets_service import SheetsService
from services.db_service import DBService
from scheduler import global_scheduler
from utils.logger import get_logs_dataframe, log_campaign_action
from utils.validator import is_truthy


def render_dashboard(
    config_manager: ConfigManager,
    auth_service: AuthService,
):
    st.title("📊 Campaign Status & Performance")
    st.caption("See how your email outreach is doing and check connections.")

    active_campaign = config_manager.get_active_campaign()
    sp_id = active_campaign.spreadsheet_id

    sheets_service = SheetsService(auth_service, sp_id) if sp_id else None
    gmail_provider = GmailProvider(auth_service) if auth_service.get_credentials() else None

    # Top Bar: Connection Health Indicators
    st.subheader("🔌 Connection Status")
    col1, col2, col3, col4, col5 = st.columns(5)

    auth_status = auth_service.get_auth_status()
    with col1:
        st.metric("Google Login", auth_status["status"], help=auth_status.get("email"))

    with col2:
        if sheets_service and sp_id:
            sh_status = sheets_service.get_connection_status()
            st.metric("Spreadsheet Source", sh_status["status"], help=sh_status.get("title", ""))
        else:
            st.metric("Spreadsheet Source", "No Sheet Link", delta="-", help="Configure Sheet URL in settings")

    with col3:
        if gmail_provider:
            gm_status = gmail_provider.test_connection()
            st.metric("Gmail Connection", gm_status["status"], help=gm_status.get("email"))
        else:
            st.metric("Gmail Connection", "Disconnected", delta="-")

    with col4:
        sched_status = global_scheduler.get_status()
        st.metric("Auto-Scheduler", sched_status["status"], help=f"Next Run: {sched_status.get('next_run')}")

    with col5:
        last_sync = active_campaign.last_sync_time or "Never"
        if last_sync != "Never":
            try:
                last_sync = datetime.fromisoformat(last_sync).strftime("%H:%M:%S")
            except Exception:
                pass
        st.metric("Last Sync with Sheet", last_sync)

    @st.dialog("Do you want to restart sending?")
    def confirm_reset_dialog():
        st.write(f"Are you sure you want to clear the sent status for all contacts in campaign **{active_campaign.name}**?")
        st.write("This will clear the record of sent emails, follow-ups, and errors.")
        st.write("All contacts will go back to being ready to receive emails.")
        
        col_yes, col_no = st.columns(2)
        with col_yes:
            if st.button("Yes, Clear & Restart", type="primary", use_container_width=True):
                email_service = EmailService(gmail_provider, sheets_service, config_manager)
                with st.spinner("Clearing sending records..."):
                    email_service.reset_campaign(active_campaign)
                st.toast("Outreach records cleared successfully!", icon="🔄")
                st.rerun()
        with col_no:
            if st.button("No, Cancel", use_container_width=True):
                st.rerun()

    # Quick Action Buttons
    st.subheader("🚀 Daily Actions")
    qcol1, qcol2, qcol3, qcol4, qcol5, qcol6 = st.columns(6)

    with qcol1:
        if st.button("🔑 Log In with Google", use_container_width=True):
            try:
                auth_service.authenticate_interactive()
                st.success("Logged in with Google successfully!")
                st.rerun()
            except Exception as e:
                st.error(f"Auth error: {e}")

    with qcol2:
        if st.button("🔄 Sync Spreadsheet", use_container_width=True):
            if sheets_service and sheets_service.connect():
                if active_campaign.data_source == "sqlite":
                    try:
                        sheet_contacts = sheets_service.read_all_contacts()
                        if sheet_contacts:
                            db_service = DBService()
                            db_service.import_contacts(active_campaign.id, sheet_contacts, overwrite=False)
                            st.toast(f"Imported {len(sheet_contacts)} people from spreadsheet!", icon="✅")
                        else:
                            st.toast("Google Sheet is empty.", icon="⚠️")
                    except Exception as e:
                        st.error(f"Failed to sync contacts: {e}")
                else:
                    st.toast("Spreadsheet synced successfully!", icon="✅")
                active_campaign.last_sync_time = datetime.now().isoformat()
                config_manager.update_campaign(active_campaign)
                st.rerun()
            else:
                st.error("Could not load Google Sheet. Please check the link.")

    # Check if we should execute send campaign from dialog confirmation
    if st.session_state.get("execute_send_campaign"):
        if not sheets_service or not gmail_provider:
            st.error("Please connect to Google and configure your spreadsheet link first.")
        else:
            email_service = EmailService(gmail_provider, sheets_service, config_manager)
            send_mode = st.session_state.get("send_mode", SendMode.NORMAL.value)
            with st.spinner("Processing email batch..."):
                res = email_service.execute_campaign_batch(active_campaign, send_mode=send_mode)
                st.success(res.get("message"))
                del st.session_state["execute_send_campaign"]
                if "send_mode" in st.session_state:
                    del st.session_state["send_mode"]
                st.rerun()

    # Check if a resend was just confirmed -> open the draft review dialog for it
    if st.session_state.get("open_draft_review"):
        del st.session_state["open_draft_review"]
        confirmed_mode = st.session_state.pop("pending_send_mode", SendMode.NORMAL.value)
        if not sheets_service or not gmail_provider:
            st.error("Please connect to Google and configure your spreadsheet link first.")
        else:
            email_service = EmailService(gmail_provider, sheets_service, config_manager)
            from ui.composer import show_draft_review_dialog
            show_draft_review_dialog(active_campaign, email_service, send_mode=confirmed_mode)

    with qcol3:
        if st.button("✉️ Start Sending Emails", use_container_width=True, type="primary"):
            if not sheets_service or not gmail_provider:
                st.error("Please connect to Google and configure your spreadsheet link first.")
            else:
                email_service = EmailService(gmail_provider, sheets_service, config_manager)
                from ui.composer import show_draft_review_dialog, confirm_resend_dialog
                analysis = email_service.analyze_resend_state(active_campaign)
                if analysis["already_sent"]:
                    confirm_resend_dialog(active_campaign, email_service, analysis)
                else:
                    show_draft_review_dialog(active_campaign, email_service, send_mode=SendMode.NORMAL.value)

    with qcol4:
        if st.button("🔔 Check & Send Follow-ups", use_container_width=True):
            if not sheets_service or not gmail_provider:
                st.error("Please connect to Google and configure your spreadsheet link first.")
            else:
                email_service = EmailService(gmail_provider, sheets_service, config_manager)
                followup_service = FollowupService(gmail_provider, sheets_service, email_service, config_manager)
                with st.spinner("Checking follow-up candidates..."):
                    res = followup_service.execute_followups_batch(active_campaign)
                    st.success(res.get("message"))
                    st.rerun()

    with qcol5:
        if st.button("🔄 Restart Campaign Status", use_container_width=True):
            confirm_reset_dialog()

    with qcol6:
        if st.button("🔄 Refresh Stats", use_container_width=True):
            st.rerun()

    st.divider()

    # Active Campaign & Analytics Metrics
    st.subheader(f"📈 Campaign Performance: '{active_campaign.name}'")

    contacts = []
    if active_campaign.data_source == "sqlite":
        db_service = DBService()
        contacts = db_service.read_all_contacts(active_campaign.id)
    elif sheets_service and sp_id:
        contacts = sheets_service.read_all_contacts()

    total_contacts = len(contacts)
    verified_count = sum(1 for c in contacts if is_truthy(c.get(COL_VERIFIED)))
    
    # Support both old and new headers for backward compatibility
    sent_count = sum(
        1 for c in contacts 
        if c.get(COL_EMAIL_SENT_DATE) or c.get("Email Sent Date") or c.get(COL_STATUS) == CampaignStatus.SENT.value
    )
    followup_count = sum(
        1 for c in contacts 
        if c.get(COL_FOLLOWUP_SENT_DATE) or c.get("Follow-up Sent Date") or c.get(COL_STATUS) == CampaignStatus.FOLLOWUP_SENT.value
    )
    responses_count = sum(1 for c in contacts if str(c.get(COL_RESPONSE_GOT, "")).strip())
    failed_count = sum(1 for c in contacts if c.get(COL_STATUS) == CampaignStatus.FAILED.value)
    pending_count = sum(
        1 for c in contacts 
        if is_truthy(c.get(COL_VERIFIED)) 
        and not c.get(COL_EMAIL_SENT_DATE) 
        and not c.get("Email Sent Date") 
        and c.get(COL_STATUS) not in (CampaignStatus.SENT.value, CampaignStatus.FOLLOWUP_SENT.value)
    )

    total_attempted = sent_count + followup_count + failed_count
    success_rate = (sent_count + followup_count) / total_attempted * 100.0 if total_attempted > 0 else 0.0

    mcol1, mcol2, mcol3, mcol4 = st.columns(4)
    with mcol1:
        st.metric("Total People", total_contacts)
        st.metric("Valid Email Addresses", verified_count)
    with mcol2:
        st.metric("Ready to Send", pending_count)
        st.metric("Initial Emails Sent", sent_count)
    with mcol3:
        st.metric("Follow-ups Sent", followup_count)
        st.metric("Replies Received", responses_count)
    with mcol4:
        st.metric("Failed to Send", failed_count)
        st.metric("Delivery Success Rate", f"{round(success_rate, 1)}%")

    st.divider()

    # Campaign Contact List
    st.subheader("👥 Recipients Status")
    if contacts:
        df_contacts = pd.DataFrame(contacts)
        display_cols = [c for c in [
            COL_FIRST_NAME, COL_EMAIL, COL_VERIFIED, COL_STATUS,
            COL_EMAIL_SENT_DATE, COL_FOLLOWUP_SENT_DATE, COL_RESPONSE_GOT
        ] if c in df_contacts.columns]
        st.dataframe(df_contacts[display_cols], use_container_width=True, hide_index=True)
    else:
        st.info("No contacts found for this campaign.")

    st.divider()

    # Recent Activity Stream
    st.subheader("📋 Recent Activity Log")
    logs_df = get_logs_dataframe()
    if not logs_df.empty:
        st.dataframe(
            logs_df[["timestamp", "action", "recipient", "status", "execution_time_ms", "error"]].head(10),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("No activity recorded yet in current session.")
