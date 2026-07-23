"""
ui/contacts.py - Interactive Contacts Explorer, Excel/CSV Importer & Database Management
"""
import streamlit as st
import pandas as pd
from config import ConfigManager
from constants import (
    COL_EMAIL,
    COL_EMAIL_SENT_DATE,
    COL_FIRST_NAME,
    COL_FOLLOWUP_SENT_DATE,
    COL_RESPONSE_GOT,
    COL_STATUS,
    COL_VERIFIED,
    COL_LAST_ERROR,
    DATA_SOURCE_GOOGLE_SHEETS,
    DATA_SOURCE_SQLITE,
    CampaignStatus,
)
from services.auth_service import AuthService
from services.sheets_service import SheetsService
from services.db_service import DBService
from utils.validator import evaluate_contact_row, is_truthy


def render_contacts(config_manager: ConfigManager, auth_service: AuthService):
    st.title("📇 Contact Lists & File Upload")
    st.caption("Upload files or check your active contact sheet here.")

    active_campaign = config_manager.get_active_campaign()
    db_service = DBService()

    # Expandable Excel / CSV Uploader Section
    with st.expander("📤 Upload an Excel or CSV File", expanded=(active_campaign.data_source == DATA_SOURCE_SQLITE)):
        st.write("Upload a spreadsheet file to save contact details in this app.")
        uploaded_file = st.file_uploader("Select spreadsheet file", type=["xlsx", "xls", "csv"], key="excel_csv_uploader")

        if uploaded_file is not None:
            try:
                if uploaded_file.name.endswith(('.xlsx', '.xls')):
                    raw_df = pd.read_excel(uploaded_file)
                else:
                    raw_df = pd.read_csv(uploaded_file)

                # Clean column headers
                raw_df.columns = [str(c).strip() for c in raw_df.columns]
                st.success(f"Parsed {len(raw_df)} rows from `{uploaded_file.name}`")

                st.subheader("Match Your File's Columns")
                cols = list(raw_df.columns)

                # Auto-guess columns
                default_email_idx = next((i for i, c in enumerate(cols) if 'email' in c.lower()), 0)
                default_fn_idx = next((i for i, c in enumerate(cols) if 'name' in c.lower() or 'first' in c.lower()), 0)
                default_ver_idx = next((i for i, c in enumerate(cols) if 'verif' in c.lower()), 0)

                col_m1, col_m2, col_m3 = st.columns(3)
                with col_m1:
                    email_col = st.selectbox("Which column has the Email addresses?", options=cols, index=default_email_idx)
                with col_m2:
                    fn_col = st.selectbox("Which column has the Names?", options=["<None>"] + cols, index=default_fn_idx + 1 if cols else 0)
                with col_m3:
                    ver_col = st.selectbox("Which column shows if the email is verified/valid?", options=["<None>"] + cols, index=default_ver_idx + 1 if cols else 0)

                # Preview mapped DataFrame
                preview_df = pd.DataFrame()
                preview_df[COL_EMAIL] = raw_df[email_col]
                preview_df[COL_FIRST_NAME] = raw_df[fn_col] if fn_col != "<None>" else ""
                preview_df[COL_VERIFIED] = raw_df[ver_col] if ver_col != "<None>" else "Yes"

                # Preserve other custom columns
                for c in cols:
                    if c not in [email_col, fn_col, ver_col]:
                        preview_df[c] = raw_df[c]

                st.markdown("**Preview of matched columns:**")
                st.dataframe(preview_df.head(), use_container_width=True, hide_index=True)

                col_btn1, col_btn2 = st.columns(2)
                with col_btn1:
                    if st.button("💾 Import & Add Contacts", type="primary", use_container_width=True):
                        records = preview_df.to_dict(orient="records")
                        count = db_service.import_contacts(active_campaign.id, records, overwrite=False)
                        # Switch campaign data source to sqlite
                        active_campaign.data_source = DATA_SOURCE_SQLITE
                        config_manager.update_campaign(active_campaign)
                        st.toast(f"Successfully saved {len(records)} contacts!", icon="✅")
                        st.rerun()

                with col_btn2:
                    if st.button("🔄 Replace All Contacts with This File", use_container_width=True):
                        records = preview_df.to_dict(orient="records")
                        count = db_service.import_contacts(active_campaign.id, records, overwrite=True)
                        active_campaign.data_source = DATA_SOURCE_SQLITE
                        config_manager.update_campaign(active_campaign)
                        st.toast(f"Replaced contacts with {len(records)} records!", icon="✅")
                        st.rerun()

            except Exception as e:
                st.error(f"Error reading file: {e}")

    st.divider()

    # Source Selection Header
    st.subheader(f"Contacts in Campaign: **{active_campaign.name}**")
    source_label = "Saved in App" if active_campaign.data_source == DATA_SOURCE_SQLITE else "Google Sheets"
    st.info(f"Storage Location: **{source_label}**")

    sp_id = active_campaign.spreadsheet_id
    contacts = []

    if active_campaign.data_source == DATA_SOURCE_SQLITE:
        contacts = db_service.read_all_contacts(active_campaign.id)
        if sp_id:
            sheets_service = SheetsService(auth_service, sp_id)
            if st.button("🔄 Fetch Fresh Contacts from Google Sheet"):
                if sheets_service.connect():
                    try:
                        sheet_contacts = sheets_service.read_all_contacts()
                        if sheet_contacts:
                            db_service.import_contacts(active_campaign.id, sheet_contacts, overwrite=False)
                            st.toast(f"Successfully synchronized {len(sheet_contacts)} contacts!", icon="✅")
                        else:
                            st.toast("Google Sheet is empty.", icon="⚠️")
                        from datetime import datetime
                        active_campaign.last_sync_time = datetime.now().isoformat()
                        config_manager.update_campaign(active_campaign)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed to sync: {e}")
                else:
                    st.error("Failed to connect to Google Sheet.")

        if not contacts and sp_id:
            st.caption("No contacts saved in app yet. Checking Google Sheet...")
            sheets_service = SheetsService(auth_service, sp_id)
            contacts = sheets_service.read_all_contacts()
    else:
        if not sp_id:
            st.warning("No Google Sheet link configured. Upload an Excel/CSV file or configure a Google Sheet link under Setup Campaigns.")
        else:
            sheets_service = SheetsService(auth_service, sp_id)
            if st.button("🔄 Fetch Fresh Contacts from Google Sheet"):
                sheets_service.connect()
                st.rerun()
            contacts = sheets_service.read_all_contacts()

    if not contacts:
        st.info("No contacts found. Please upload an Excel/CSV spreadsheet above to start outreach.")
        return

    df = pd.DataFrame(contacts)

    # Search & Filter controls
    col1, col2, col3 = st.columns(3)
    with col1:
        search_query = st.text_input("🔍 Search Contacts:", placeholder="e.g. John").strip().lower()

    with col2:
        statuses = ["ALL"] + sorted(list(set(df[COL_STATUS].astype(str).tolist()))) if COL_STATUS in df.columns else ["ALL"]
        status_filter = st.selectbox("Filter by Status:", statuses)

    with col3:
        verified_filter = st.selectbox("Filter by Verification:", ["All Contacts", "Verified/Valid Only", "Unverified Only"])

    # Apply filters
    filtered_df = df.copy()

    if search_query:
        name_match = filtered_df[COL_FIRST_NAME].astype(str).str.lower().str.contains(search_query) if COL_FIRST_NAME in filtered_df.columns else pd.Series([False]*len(filtered_df))
        email_match = filtered_df[COL_EMAIL].astype(str).str.lower().str.contains(search_query) if COL_EMAIL in filtered_df.columns else pd.Series([False]*len(filtered_df))
        filtered_df = filtered_df[name_match | email_match]

    if status_filter != "ALL" and COL_STATUS in filtered_df.columns:
        filtered_df = filtered_df[filtered_df[COL_STATUS].astype(str) == status_filter]

    if verified_filter == "Verified/Valid Only" and COL_VERIFIED in filtered_df.columns:
        filtered_df = filtered_df[filtered_df[COL_VERIFIED].apply(is_truthy)]
    elif verified_filter == "Unverified Only" and COL_VERIFIED in filtered_df.columns:
        filtered_df = filtered_df[~filtered_df[COL_VERIFIED].apply(is_truthy)]

    st.markdown(f"**Showing {len(filtered_df)} of {len(df)} people**")

    # Interactive Table
    display_cols = [c for c in [
        COL_FIRST_NAME, COL_EMAIL, COL_VERIFIED, COL_STATUS,
        COL_EMAIL_SENT_DATE, COL_FOLLOWUP_SENT_DATE, COL_RESPONSE_GOT, COL_LAST_ERROR
    ] if c in filtered_df.columns]

    st.dataframe(filtered_df[display_cols], use_container_width=True, hide_index=True)

    # Download Buttons
    csv_data = filtered_df.to_csv(index=False)
    col_dl1, col_dl2 = st.columns(2)
    with col_dl1:
        st.download_button(
            "📥 Download List as CSV File",
            data=csv_data,
            file_name="campaign_contacts.csv",
            mime="text/csv",
            use_container_width=True,
        )
    with col_dl2:
        import io
        buffer = io.BytesIO()
        try:
            with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                filtered_df[display_cols].to_excel(writer, index=False, sheet_name='Contacts')
            excel_data = buffer.getvalue()
            st.download_button(
                "📥 Download List as Excel File",
                data=excel_data,
                file_name="campaign_contacts.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
        except Exception as e:
            st.error(f"Error generating Excel: {e}")

    st.divider()

    # Skipped & Invalid Breakdown Section
    st.subheader("⚠️ Warnings & Skipped Contacts")
    seen_emails = set()
    skipped_records = []

    for row in contacts:
        eval_res = evaluate_contact_row(row, seen_emails)
        if not eval_res["can_send"]:
            skipped_records.append({
                "First Name": row.get(COL_FIRST_NAME, ""),
                "Email": row.get(COL_EMAIL, ""),
                "Status": row.get(COL_STATUS, CampaignStatus.PENDING.value),
                "Skip Reason": eval_res["reason"],
            })

    if skipped_records:
        st.dataframe(pd.DataFrame(skipped_records), use_container_width=True, hide_index=True)
    else:
        st.success("All contacts are set up correctly and ready to receive emails!")
