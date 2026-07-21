"""
ui/logs.py - Application & Campaign Action Logs Page
"""
import streamlit as st
import pandas as pd
from utils.logger import export_logs_to_csv, get_logs_dataframe


def render_logs():
    st.title("📜 Application & Campaign Activity Logs")
    st.caption("View real-time event logs, execution times, retry counts, and export log reports.")

    df = get_logs_dataframe()

    col1, col2 = st.columns([2, 1])
    with col1:
        search_query = st.text_input("🔍 Search Logs:", placeholder="Filter by email, action, error...").strip().lower()
    with col2:
        level_filter = st.selectbox("Log Level:", ["ALL", "INFO", "WARNING", "ERROR"])

    filtered_df = df.copy()
    if not filtered_df.empty:
        if level_filter != "ALL":
            filtered_df = filtered_df[filtered_df["level"] == level_filter]

        if search_query:
            msg_match = filtered_df["message"].astype(str).str.lower().str.contains(search_query)
            recip_match = filtered_df["recipient"].astype(str).str.lower().str.contains(search_query)
            act_match = filtered_df["action"].astype(str).str.lower().str.contains(search_query)
            filtered_df = filtered_df[msg_match | recip_match | act_match]

        st.markdown(f"**Displaying {len(filtered_df)} log records**")
        st.dataframe(filtered_df, use_container_width=True, hide_index=True)
    else:
        st.info("No log records available in current session.")

    st.divider()

    csv_data = export_logs_to_csv()
    st.download_button(
        label="📥 Download Campaign Logs CSV",
        data=csv_data,
        file_name="campaign_activity_logs.csv",
        mime="text/csv",
        use_container_width=True,
    )
