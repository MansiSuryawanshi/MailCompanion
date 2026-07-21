"""
ui/analytics.py - Time-framed Campaign Analytics & Performance Charts Page
"""
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta

from config import ConfigManager
from constants import (
    COL_EMAIL_SENT_DATE,
    COL_FOLLOWUP_SENT_DATE,
    COL_RESPONSE_GOT,
    COL_STATUS,
    CampaignStatus,
)
from services.auth_service import AuthService
from services.sheets_service import SheetsService
from services.db_service import DBService


def render_analytics(config_manager: ConfigManager, auth_service: AuthService):
    st.title("📊 Campaign Analytics & Insights")
    st.caption("Performance stats over customizable time frames: Today, Yesterday, Last 7 Days, Last 30 Days.")

    active_campaign = config_manager.get_active_campaign()
    sp_id = active_campaign.spreadsheet_id

    time_frame = st.selectbox("Select Time Frame:", ["Today", "Yesterday", "Last 7 Days", "Last 30 Days", "All Time"])

    contacts = []
    if active_campaign.data_source == "sqlite":
        db_service = DBService()
        contacts = db_service.read_all_contacts(active_campaign.id)
    elif sp_id:
        sheets_service = SheetsService(auth_service, sp_id)
        contacts = sheets_service.read_all_contacts()
    else:
        st.warning("No contact source (Google Sheet or SQLite database) configured for active campaign.")
        return

    if not contacts:
        st.info("No data available in current contact source for analysis.")
        return

    now = datetime.now()
    if time_frame == "Today":
        start_dt = datetime(now.year, now.month, now.day)
        end_dt = now
    elif time_frame == "Yesterday":
        start_dt = datetime(now.year, now.month, now.day) - timedelta(days=1)
        end_dt = datetime(now.year, now.month, now.day)
    elif time_frame == "Last 7 Days":
        start_dt = now - timedelta(days=7)
        end_dt = now
    elif time_frame == "Last 30 Days":
        start_dt = now - timedelta(days=30)
        end_dt = now
    else:
        start_dt = datetime(2000, 1, 1)
        end_dt = now

    def parse_dt(dt_str: str) -> bool:
        if not dt_str:
            return False
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(str(dt_str).strip(), fmt)
                return start_dt <= dt <= end_dt
            except ValueError:
                pass
        return False

    sent_period = sum(
        1 for c in contacts 
        if parse_dt(c.get(COL_EMAIL_SENT_DATE) or c.get("Email Sent Date"))
    )
    followup_period = sum(
        1 for c in contacts 
        if parse_dt(c.get(COL_FOLLOWUP_SENT_DATE) or c.get("Follow-up Sent Date"))
    )
    responses_period = sum(1 for c in contacts if str(c.get(COL_RESPONSE_GOT, "")).strip())
    failed_period = sum(1 for c in contacts if c.get(COL_STATUS) == CampaignStatus.FAILED.value)

    total_attempted = sent_period + followup_period + failed_period
    success_rate = ((sent_period + followup_period) / total_attempted * 100.0) if total_attempted > 0 else 0.0

    mcol1, mcol2, mcol3, mcol4, mcol5 = st.columns(5)
    mcol1.metric("Emails Sent", sent_period)
    mcol2.metric("Follow-ups", followup_period)
    mcol3.metric("Responses", responses_period)
    mcol4.metric("Failures", failed_period)
    mcol5.metric("Success Rate", f"{round(success_rate, 1)}%")

    st.divider()

    st.subheader("📊 Delivery & Action Breakdown")
    chart_data = pd.DataFrame({
        "Metric": ["Initial Sent", "Follow-ups Sent", "Responses", "Failures"],
        "Count": [sent_period, followup_period, responses_period, failed_period]
    })
    st.bar_chart(chart_data, x="Metric", y="Count")
