"""
ui/campaigns.py - Multi-Campaign Management Page
"""
import streamlit as st
from config import Campaign, ConfigManager, extract_spreadsheet_id
from constants import CampaignState


def render_campaigns(config_manager: ConfigManager):
    st.title("🎯 Multi-Campaign Manager")
    st.caption("Create, edit, duplicate, archive, and manage state across email campaigns.")

    campaigns = config_manager.campaigns
    active_campaign = config_manager.get_active_campaign()

    # Active Campaign Selection Header
    st.subheader("📌 Active Campaign Selector")
    c_options = {c_id: f"{c.name} [{c.state}]" for c_id, c in campaigns.items()}
    selected_id = st.selectbox(
        "Select Active Working Campaign:",
        options=list(c_options.keys()),
        format_func=lambda x: c_options[x],
        index=list(c_options.keys()).index(active_campaign.id) if active_campaign.id in c_options else 0,
    )

    if selected_id != active_campaign.id:
        config_manager.set_active_campaign(selected_id)
        st.toast(f"Switched active campaign to '{campaigns[selected_id].name}'", icon="🎯")
        st.rerun()

    current_c = config_manager.get_active_campaign()

    st.divider()

    # Top Control Bar for Current Campaign
    col_left, col_right = st.columns([2, 1])

    with col_left:
        st.markdown(f"### Current Campaign: **{current_c.name}**")
        st.write(f"**ID:** `{current_c.id}` | **Created:** {current_c.created_at[:10]}")
        st.write(f"**Google Sheet URL:** `{current_c.spreadsheet_url or 'Not configured'}`")

    with col_right:
        st.markdown("#### Campaign State")
        state_options = [s.value for s in CampaignState]
        new_state = st.selectbox(
            "State:",
            options=state_options,
            index=state_options.index(current_c.state) if current_c.state in state_options else 0,
            key="campaign_state_select",
        )
        if new_state != current_c.state:
            current_c.state = new_state
            config_manager.update_campaign(current_c)
            st.toast(f"Campaign state updated to '{new_state}'", icon="⚙️")
            st.rerun()

    st.divider()

    # Tabs: Campaign Settings & Action Operations
    tab_edit, tab_create, tab_actions = st.tabs(["📝 Edit Selected Campaign", "➕ Create New Campaign", "⚙️ Actions & Management"])

    with tab_edit:
        with st.form("edit_campaign_form"):
            c_name = st.text_input("Campaign Name", value=current_c.name)
            
            c_data_source = st.radio(
                "Contact Data Source:",
                options=["sqlite", "google_sheets"],
                format_func=lambda x: "Local SQLite Database (Excel/CSV upload)" if x == "sqlite" else "Google Sheets URL",
                index=0 if current_c.data_source == "sqlite" else 1,
                horizontal=True,
            )

            c_url = st.text_input("Google Sheet URL or Spreadsheet ID (Optional if using SQLite):", value=current_c.spreadsheet_url)

            col1, col2 = st.columns(2)
            with col1:
                c_min_delay = st.number_input("Min Send Delay (seconds)", value=float(current_c.min_send_delay), min_value=1.0, max_value=60.0, step=0.5)
                c_followup_days = st.number_input("Follow-up Delay (days)", value=int(current_c.followup_days), min_value=1, max_value=30)
            with col2:
                c_max_delay = st.number_input("Max Send Delay (seconds)", value=float(current_c.max_send_delay), min_value=1.0, max_value=60.0, step=0.5)
                c_daily_limit = st.number_input("Daily Send Limit", value=int(current_c.daily_limit), min_value=1, max_value=5000)

            c_draft_mode = st.checkbox("Enable Gmail Draft Mode (Create drafts instead of sending)", value=current_c.draft_mode)

            submitted = st.form_submit_button("Save Campaign Settings", type="primary")
            if submitted:
                current_c.name = c_name
                current_c.data_source = c_data_source
                current_c.spreadsheet_url = c_url
                current_c.spreadsheet_id = extract_spreadsheet_id(c_url)
                current_c.min_send_delay = c_min_delay
                current_c.max_send_delay = c_max_delay
                current_c.followup_days = c_followup_days
                current_c.daily_limit = c_daily_limit
                current_c.draft_mode = c_draft_mode
                config_manager.update_campaign(current_c)
                st.success("Campaign settings updated successfully!")
                st.rerun()

    with tab_create:
        with st.form("create_campaign_form"):
            new_name = st.text_input("New Campaign Name", placeholder="e.g. Q3 Sales Outreach")
            new_url = st.text_input("Google Sheet URL", placeholder="https://docs.google.com/spreadsheets/d/...")

            create_submit = st.form_submit_button("Create Campaign", type="primary")
            if create_submit:
                if not new_name.strip():
                    st.error("Please provide a campaign name.")
                else:
                    new_c = config_manager.create_campaign(new_name.strip(), new_url.strip())
                    st.success(f"Campaign '{new_c.name}' created and set as active!")
                    st.rerun()

    with tab_actions:
        st.subheader("Manage Campaigns List")
        col_act1, col_act2, col_act3 = st.columns(3)

        with col_act1:
            if st.button("📋 Duplicate Campaign", use_container_width=True):
                dup = config_manager.duplicate_campaign(current_c.id)
                if dup:
                    st.success(f"Duplicated campaign as '{dup.name}'")
                    st.rerun()

        with col_act2:
            if st.button("📁 Archive Campaign", use_container_width=True):
                current_c.state = CampaignState.ARCHIVED.value
                config_manager.update_campaign(current_c)
                st.info(f"Archived campaign '{current_c.name}'")
                st.rerun()

        with col_act3:
            if st.button("🗑️ Delete Campaign", use_container_width=True, type="secondary"):
                if len(config_manager.campaigns) <= 1:
                    st.warning("Cannot delete the only remaining campaign.")
                else:
                    del_name = current_c.name
                    if config_manager.delete_campaign(current_c.id):
                        st.success(f"Deleted campaign '{del_name}'")
                        st.rerun()
