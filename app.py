"""
app.py - Automated Email Campaign Manager Main Entry Point & Page Router
"""
import os
import streamlit as st

from config import ConfigManager
from services.auth_service import AuthService
from scheduler import global_scheduler
from ui.analytics import render_analytics
from ui.campaigns import render_campaigns
from ui.composer import render_composer
from ui.contacts import render_contacts
from ui.dashboard import render_dashboard
from ui.logs import render_logs
from ui.settings import render_settings

# Set Page Config
st.set_page_config(
    page_title="Automated Email Campaign Manager",
    page_icon="📧",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom Styling (Dark/Light Modern Glassmorphism Aesthetic)
st.markdown("""
<style>
    .main {
        padding-top: 1.5rem;
    }
    .stMetric {
        background: rgba(255, 255, 255, 0.05);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 10px;
        padding: 15px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    .stButton>button {
        border-radius: 8px;
        font-weight: 500;
    }
    .status-badge {
        display: inline-block;
        padding: 4px 8px;
        border-radius: 12px;
        font-size: 12px;
        font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)


def main():
    # Initialize Core Services & Managers
    config_manager = ConfigManager()
    auth_service = AuthService()

    # Launch Scheduler if configured
    if config_manager.settings.get("scheduler_enabled") and not global_scheduler.get_status()["is_running"]:
        sched_time = config_manager.settings.get("scheduler_time", "10:00")
        global_scheduler.start(sched_time)

    # Sidebar Navigation
    st.sidebar.title("📧 Campaign Manager")
    active_campaign = config_manager.get_active_campaign()
    st.sidebar.caption(f"Active Campaign: **{active_campaign.name}**")
    st.sidebar.caption(f"State: **{active_campaign.state}**")

    st.sidebar.divider()

    page = st.sidebar.radio(
        "Navigation Menu",
        [
            "📊 Dashboard",
            "🎯 Campaigns",
            "✍️ Email Composer",
            "📇 Contacts",
            "📈 Analytics",
            "📜 Logs",
            "⚙️ Settings",
        ],
    )

    st.sidebar.divider()
    st.sidebar.markdown("### 💡 Quick Status")
    auth_status = auth_service.get_auth_status()
    st.sidebar.markdown(f"**Google Auth:** `{auth_status['status']}`")
    sched_info = global_scheduler.get_status()
    st.sidebar.markdown(f"**Scheduler:** `{sched_info['status']}`")

    # Page Router
    if page == "📊 Dashboard":
        render_dashboard(config_manager, auth_service)
    elif page == "🎯 Campaigns":
        render_campaigns(config_manager)
    elif page == "✍️ Email Composer":
        render_composer(config_manager, auth_service)
    elif page == "📇 Contacts":
        render_contacts(config_manager, auth_service)
    elif page == "📈 Analytics":
        render_analytics(config_manager, auth_service)
    elif page == "📜 Logs":
        render_logs()
    elif page == "⚙️ Settings":
        render_settings(config_manager, auth_service)


if __name__ == "__main__":
    main()
