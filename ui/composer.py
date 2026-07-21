"""
ui/composer.py - Email Composer, Template Editor, Live Preview, Dry-Run & Execution Page
"""
import streamlit as st
import streamlit.components.v1 as components
from config import ConfigManager
from services.auth_service import AuthService
from services.email_service import EmailService
from services.gmail_provider import GmailProvider
from services.sheets_service import SheetsService
from utils.logger import get_logs_dataframe


def render_composer(config_manager: ConfigManager, auth_service: AuthService):
    st.title("✍️ Email Composer & Campaign Execution")
    st.caption("Design personalized templates, preview live dynamic emails, execute dry runs, and dispatch campaign emails.")

    active_campaign = config_manager.get_active_campaign()
    sp_id = active_campaign.spreadsheet_id

    sheets_service = SheetsService(auth_service, sp_id) if sp_id else None
    gmail_provider = GmailProvider(auth_service) if auth_service.get_credentials() else None

    # Variable Helper Chips
    st.info("💡 **Supported Dynamic Variables:** `{{first_name}}`, `{{email}}`, `{{current_date}}`, `{{sender_name}}` plus any header in your Google Sheet.")

    tab_compose, tab_preview, tab_dryrun, tab_send = st.tabs(["📝 Email Templates", "👁️ Live Preview", "🧪 Dry Run Analysis", "🚀 Send / Dispatch"])

    with tab_compose:
        st.subheader("Initial Email Template")
        init_subj = st.text_input("Initial Email Subject", value=active_campaign.initial_subject)
        init_body = st.text_area("Initial Email Body (HTML or Text)", value=active_campaign.initial_body, height=180)

        st.subheader("Follow-up Email Template")
        follow_subj = st.text_input("Follow-up Email Subject", value=active_campaign.followup_subject)
        follow_body = st.text_area("Follow-up Email Body (HTML or Text)", value=active_campaign.followup_body, height=180)

        if st.button("💾 Save Templates to Campaign", type="primary"):
            active_campaign.initial_subject = init_subj
            active_campaign.initial_body = init_body
            active_campaign.followup_subject = follow_subj
            active_campaign.followup_body = follow_body
            config_manager.update_campaign(active_campaign)
            st.success("Templates saved successfully!")

    with tab_preview:
        st.subheader("Live Email Preview")
        preview_mode = st.radio("Preview Type:", ["Initial Email", "Follow-up Email"], horizontal=True)

        sample_name = st.text_input("Sample First Name", value="Alex")
        sample_email = st.text_input("Sample Email", value="alex.sample@example.com")

        if sheets_service and gmail_provider:
            email_service = EmailService(gmail_provider, sheets_service, config_manager)
            sample_row = {"First Name": sample_name, "Email": sample_email, "Verified": "Yes"}
            is_f = (preview_mode == "Follow-up Email")
            subj, body_html = email_service.render_email_content(active_campaign, sample_row, is_followup=is_f)

            st.markdown(f"**Rendered Subject:** `{subj}`")
            st.markdown("---")
            st.markdown("**Rendered HTML Output:**")
            components.html(body_html, height=300, scrolling=True)

    with tab_dryrun:
        st.subheader("Dry Run Analysis")
        st.write("Simulates campaign execution without sending emails or updating the Google Sheet.")

        if st.button("🧪 Run Dry Run Analysis", type="primary"):
            if not sheets_service or not gmail_provider or not sp_id:
                st.error("Google Authentication and valid Sheet URL required.")
            else:
                email_service = EmailService(gmail_provider, sheets_service, config_manager)
                with st.spinner("Analyzing sheet contacts and rules..."):
                    report = email_service.run_dry_run(active_campaign)

                col1, col2, col3, col4 = st.columns(4)
                col1.metric("Will Send", report["will_send_count"])
                col2.metric("Already Sent", report["already_sent_count"])
                col3.metric("Skipped", report["skipped_count"])
                col4.metric("Est. Duration", f"{report['estimated_duration_sec']}s")

                st.divider()

                if report["will_send"]:
                    st.subheader("Emails That Will Be Sent")
                    st.dataframe(report["will_send"], use_container_width=True)

                if report["skipped"]:
                    st.subheader("Skipped Contacts & Reasons")
                    st.dataframe(report["skipped"], use_container_width=True)

    with tab_send:
        st.subheader("Campaign Send Execution & Test Mode")

        # Test Send Section
        with st.expander("✉️ Send Test Email", expanded=False):
            test_addr = st.text_input("Test Recipient Email Address:")
            test_type = st.radio("Test Email Type:", ["Initial", "Follow-up"], horizontal=True)
            if st.button("Send Test Email Now"):
                if not test_addr:
                    st.error("Enter test recipient email address.")
                elif not gmail_provider or not sheets_service:
                    st.error("Google Authentication required.")
                else:
                    email_service = EmailService(gmail_provider, sheets_service, config_manager)
                    with st.spinner("Sending test email..."):
                        res = email_service.send_test_email(active_campaign, test_addr, is_followup=(test_type == "Follow-up"))
                        if res["success"]:
                            st.success(f"Test email sent successfully to {test_addr}!")
                        else:
                            st.error(f"Test send failed: {res.get('error')}")

        st.divider()

        # Batch Send Execution Section
        st.subheader("🚀 Dispatch Campaign Emails")
        draft_mode = active_campaign.draft_mode
        st.warning(f"**Mode:** {'GMAIL DRAFT MODE (Drafts only)' if draft_mode else 'LIVE SEND MODE (Sends real emails)'}")

        retry_failed = st.checkbox("Retry Failed Emails Only", value=False)

        if st.button("🔥 START CAMPAIGN SEND NOW", type="primary", use_container_width=True):
            if not sheets_service or not gmail_provider or not sp_id:
                st.error("Google Auth and valid Sheet URL required.")
            else:
                email_service = EmailService(gmail_provider, sheets_service, config_manager)

                progress_bar = st.progress(0.0)
                status_text = st.empty()
                metrics_placeholder = st.empty()

                def update_progress(data: dict):
                    pct = data["progress"]
                    progress_bar.progress(pct)
                    status_text.markdown(f"**Processing {data['current']}/{data['total']}:** Sending to `{data['contact_email']}`...")
                    metrics_placeholder.markdown(
                        f"**Sent:** {data['sent_count']} | **Failed:** {data['failed_count']} | **ETA Remaining:** {data['eta_seconds']}s"
                    )

                with st.spinner("Dispatching campaign..."):
                    res = email_service.execute_campaign_batch(
                        active_campaign, progress_callback=update_progress, retry_failed_only=retry_failed
                    )

                progress_bar.progress(1.0)
                st.success(res["message"])
                st.rerun()
