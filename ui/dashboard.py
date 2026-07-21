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
    st.title("📊 Campaign Overview & Health Dashboard")
    st.caption("Real-time monitoring of connection health, campaign metrics, and system activity.")

    active_campaign = config_manager.get_active_campaign()
    sp_id = active_campaign.spreadsheet_id

    sheets_service = SheetsService(auth_service, sp_id) if sp_id else None
    gmail_provider = GmailProvider(auth_service) if auth_service.get_credentials() else None

    # Top Bar: Connection Health Indicators
    st.subheader("🔌 System Health & Status")
    col1, col2, col3, col4, col5 = st.columns(5)

    auth_status = auth_service.get_auth_status()
    with col1:
        st.metric("Google OAuth", auth_status["status"], help=auth_status.get("email"))

    with col2:
        if sheets_service and sp_id:
            sh_status = sheets_service.get_connection_status()
            st.metric("Google Sheet", sh_status["status"], help=sh_status.get("title", ""))
        else:
            st.metric("Google Sheet", "No Sheet URL", delta="-", help="Configure Sheet URL in settings")

    with col3:
        if gmail_provider:
            gm_status = gmail_provider.test_connection()
            st.metric("Gmail API", gm_status["status"], help=gm_status.get("email"))
        else:
            st.metric("Gmail API", "Disconnected", delta="-")

    with col4:
        sched_status = global_scheduler.get_status()
        st.metric("Scheduler", sched_status["status"], help=f"Next Run: {sched_status.get('next_run')}")

    with col5:
        last_sync = active_campaign.last_sync_time or "Never"
        if last_sync != "Never":
            try:
                last_sync = datetime.fromisoformat(last_sync).strftime("%H:%M:%S")
            except Exception:
                pass
        st.metric("Last Sync", last_sync)

    st.divider()

    # Quick Action Buttons
    st.subheader("🚀 Quick Actions")
    qcol1, qcol2, qcol3, qcol4, qcol5 = st.columns(5)

    with qcol1:
        if st.button("🔑 Connect Google", use_container_width=True):
            try:
                auth_service.authenticate_interactive()
                st.success("Google Account authenticated!")
                st.rerun()
            except Exception as e:
                st.error(f"Auth error: {e}")

    with qcol2:
        if st.button("🔄 Sync Sheet", use_container_width=True):
            if sheets_service and sheets_service.connect():
                active_campaign.last_sync_time = datetime.now().isoformat()
                config_manager.update_campaign(active_campaign)
                st.toast("Google Sheet synchronized!", icon="✅")
                st.rerun()
            else:
                st.error("Failed to connect to Google Sheet.")

    with qcol3:
        if st.button("✉️ Send Emails Now", use_container_width=True, type="primary"):
            if not sheets_service or not gmail_provider:
                st.error("Authenticate Google & configure Sheet URL first.")
            else:
                email_service = EmailService(gmail_provider, sheets_service, config_manager)
                with st.spinner("Processing email batch..."):
                    res = email_service.execute_campaign_batch(active_campaign)
                    st.success(res.get("message"))
                    st.rerun()

    with qcol4:
        if st.button("🔔 Check Follow-ups", use_container_width=True):
            if not sheets_service or not gmail_provider:
                st.error("Authenticate Google & configure Sheet URL first.")
            else:
                email_service = EmailService(gmail_provider, sheets_service, config_manager)
                followup_service = FollowupService(gmail_provider, sheets_service, email_service, config_manager)
                with st.spinner("Checking follow-up candidates..."):
                    res = followup_service.execute_followups_batch(active_campaign)
                    st.success(res.get("message"))
                    st.rerun()

    with qcol5:
        if st.button("🔄 Refresh Dashboard", use_container_width=True):
            st.rerun()

    st.divider()

    # Active Campaign & Analytics Metrics
    st.subheader(f"📈 Campaign Metrics: '{active_campaign.name}'")

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
        st.metric("Total Contacts", total_contacts)
        st.metric("Verified Contacts", verified_count)
    with mcol2:
        st.metric("Pending Emails", pending_count)
        st.metric("Emails Sent", sent_count)
    with mcol3:
        st.metric("Follow-ups Sent", followup_count)
        st.metric("Responses Received", responses_count)
    with mcol4:
        st.metric("Failed Emails", failed_count)
        st.metric("Success Rate", f"{round(success_rate, 1)}%")

    st.divider()

    # Campaign Contact List
    st.subheader("👥 Campaign Contact List")
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
    st.subheader("📋 Recent Activity Stream")
    logs_df = get_logs_dataframe()
    if not logs_df.empty:
        st.dataframe(
            logs_df[["timestamp", "action", "recipient", "status", "execution_time_ms", "error"]].head(10),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("No activity recorded yet in current session.")
