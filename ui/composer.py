"""
ui/composer.py - Email Composer, Template Editor, Live Preview, Dry-Run & Execution Page
"""
import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
from config import ConfigManager
from constants import SendMode
from services.auth_service import AuthService
from services.email_service import EmailService, format_elapsed
from services.gmail_provider import GmailProvider
from services.sheets_service import SheetsService
from utils.logger import get_logs_dataframe


def save_composer_templates(campaign, config_manager):
    updated = False
    if "init_subj_input" in st.session_state and st.session_state["init_subj_input"] != campaign.initial_subject:
        campaign.initial_subject = st.session_state["init_subj_input"]
        updated = True
    if "init_body_input" in st.session_state and st.session_state["init_body_input"] != campaign.initial_body:
        campaign.initial_body = st.session_state["init_body_input"]
        updated = True
    if "follow_subj_input" in st.session_state and st.session_state["follow_subj_input"] != campaign.followup_subject:
        campaign.followup_subject = st.session_state["follow_subj_input"]
        updated = True
    if "follow_body_input" in st.session_state and st.session_state["follow_body_input"] != campaign.followup_body:
        campaign.followup_body = st.session_state["follow_body_input"]
        updated = True
    if updated:
        config_manager.update_campaign(campaign)


def render_composer(config_manager: ConfigManager, auth_service: AuthService):
    st.title("✍️ Write & Send Emails")
    st.caption("Write your templates, preview personal emails, test them, and send your campaign.")

    active_campaign = config_manager.get_active_campaign()
    
    # Auto-save templates if edited in composer inputs
    save_composer_templates(active_campaign, config_manager)

    sp_id = active_campaign.spreadsheet_id

    sheets_service = SheetsService(auth_service, sp_id) if sp_id else None
    gmail_provider = GmailProvider(auth_service) if auth_service.get_credentials() else None

    # Variable Helper Chips
    st.info("💡 **Personalized Tags you can use:** Insert `{{first_name}}`, `{{email}}`, `{{current_date}}`, or `{{sender_name}}`. You can also use any column header name from your spreadsheet.")

    tab_compose, tab_preview, tab_dryrun, tab_send = st.tabs(["📝 Write Templates", "👁️ Preview Emails", "🧪 Run a Test Simulation", "🚀 Send Campaign"])

    with tab_compose:
        st.subheader("First Email Template")
        init_subj = st.text_input("First Email Subject Line", value=active_campaign.initial_subject, key="init_subj_input")
        init_body = st.text_area("First Email Message Content", value=active_campaign.initial_body, height=180, key="init_body_input")

        st.subheader("Follow-up Email Template")
        follow_subj = st.text_input("Follow-up Email Subject Line", value=active_campaign.followup_subject, key="follow_subj_input")
        follow_body = st.text_area("Follow-up Email Message Content", value=active_campaign.followup_body, height=180, key="follow_body_input")

        if st.button("💾 Save Templates", type="primary"):
            active_campaign.initial_subject = init_subj
            active_campaign.initial_body = init_body
            active_campaign.followup_subject = follow_subj
            active_campaign.followup_body = follow_body
            config_manager.update_campaign(active_campaign)
            st.success("Message templates saved successfully!")

    with tab_preview:
        st.subheader("Live Preview")
        preview_mode = st.radio("Choose email to preview:", ["First Email", "Follow-up Email"], horizontal=True)

        sample_name = st.text_input("Test Name", value="Alex")
        sample_email = st.text_input("Test Email Address", value="alex.sample@example.com")

        if sheets_service and gmail_provider:
            email_service = EmailService(gmail_provider, sheets_service, config_manager)
            sample_row = {"First Name": sample_name, "Email": sample_email, "Verified": "Yes"}
            is_f = (preview_mode == "Follow-up Email")
            subj, body_html = email_service.render_email_content(active_campaign, sample_row, is_followup=is_f)

            st.markdown(f"**Preview of Subject Line:** `{subj}`")
            st.markdown("---")
            st.markdown("**Preview of Message Content:**")
            components.html(body_html, height=300, scrolling=True)

    with tab_dryrun:
        st.subheader("Simulation (No emails will actually be sent)")
        st.write("Check how many emails will be sent or skipped before you start.")

        if st.button("🧪 Run Test Simulation", type="primary"):
            if not sheets_service or not gmail_provider or not sp_id:
                st.error("Please connect to Google and configure your spreadsheet link first.")
            else:
                email_service = EmailService(gmail_provider, sheets_service, config_manager)
                with st.spinner("Checking spreadsheet contacts and outreach rules..."):
                    report = email_service.run_dry_run(active_campaign)

                col1, col2, col3, col4 = st.columns(4)
                col1.metric("Emails to Send", report["will_send_count"])
                col2.metric("Already Sent Before", report["already_sent_count"])
                col3.metric("Will Be Skipped", report["skipped_count"])
                col4.metric("Estimated Time", f"{report['estimated_duration_sec']}s")

                st.divider()

                if report["will_send"]:
                    st.subheader("List of Emails That Will Go Out")
                    st.dataframe(report["will_send"], use_container_width=True)

                if report["skipped"]:
                    st.subheader("Contacts That Will Be Skipped & Why")
                    st.dataframe(report["skipped"], use_container_width=True)

    with tab_send:
        st.subheader("Campaign Sending & Testing")

        # Test Send Section
        with st.expander("✉️ Send a Test Email to Yourself", expanded=False):
            test_addr = st.text_input("Send test email to:")
            test_type = st.radio("Type of test email:", ["First", "Follow-up"], horizontal=True)
            if st.button("Send Test Email"):
                if not test_addr:
                    st.error("Please enter a test email address.")
                elif not gmail_provider or not sheets_service:
                    st.error("Please connect to Google first.")
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
        st.subheader("🚀 Start the Outreach Campaign")
        draft_mode = active_campaign.draft_mode
        st.warning(f"**Mode:** {'Safe Mode: Creating drafts in Gmail (Go to Gmail to review and send them)' if draft_mode else 'Live Mode: Sending emails directly to recipients now'}")

        retry_failed = st.checkbox("Only retry emails that failed previously", value=False)

        # Check if we should execute send campaign from dialog confirmation
        if st.session_state.get("execute_send_campaign"):
            if not sheets_service or not gmail_provider or not sp_id:
                st.error("Please connect to Google and configure your spreadsheet link first.")
            else:
                email_service = EmailService(gmail_provider, sheets_service, config_manager)
                send_mode = st.session_state.get("send_mode", SendMode.NORMAL.value)
                target_emails = st.session_state.get("target_emails")

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

                with st.spinner("Sending campaign emails..."):
                    res = email_service.execute_campaign_batch(
                        active_campaign, progress_callback=update_progress, send_mode=send_mode, target_emails=target_emails
                    )

                progress_bar.progress(1.0)
                st.success(res["message"])
                del st.session_state["execute_send_campaign"]
                if "send_mode" in st.session_state:
                    del st.session_state["send_mode"]
                if "target_emails" in st.session_state:
                    del st.session_state["target_emails"]
                st.rerun()

        # Check if a resend was just confirmed -> open the draft review dialog for it
        if st.session_state.get("open_draft_review"):
            del st.session_state["open_draft_review"]
            confirmed_mode = st.session_state.pop("pending_send_mode", SendMode.NORMAL.value)
            confirmed_targets = st.session_state.pop("pending_target_emails", None)
            if not sheets_service or not gmail_provider or not sp_id:
                st.error("Please connect to Google and configure your spreadsheet link first.")
            else:
                email_service = EmailService(gmail_provider, sheets_service, config_manager)
                show_draft_review_dialog(active_campaign, email_service, send_mode=confirmed_mode, target_emails=confirmed_targets)

        if st.button("🚀 START SENDING EMAILS NOW", type="primary", use_container_width=True):
            if not sheets_service or not gmail_provider or not sp_id:
                st.error("Please connect to Google and configure your spreadsheet link first.")
            elif retry_failed:
                email_service = EmailService(gmail_provider, sheets_service, config_manager)
                show_draft_review_dialog(active_campaign, email_service, send_mode=SendMode.RETRY_FAILED.value)
            else:
                email_service = EmailService(gmail_provider, sheets_service, config_manager)
                analysis = email_service.analyze_resend_state(active_campaign)
                if analysis["already_sent"]:
                    confirm_resend_dialog(active_campaign, email_service, analysis)
                else:
                    show_draft_review_dialog(active_campaign, email_service, send_mode=SendMode.NORMAL.value)


@st.dialog("Review First Email Draft")
def show_draft_review_dialog(campaign, email_service, send_mode=SendMode.NORMAL.value, target_emails=None):
    if send_mode == SendMode.SELECTED.value and target_emails:
        st.write(f"Review how the email looks before sending to the **{len(target_emails)}** people you selected:")
    else:
        st.write("Review how the email looks for the first person before sending the campaign:")

    # Retrieve contacts to preview the first matching email
    try:
        contacts = email_service.get_contacts(campaign)
    except Exception as e:
        st.error(f"Failed to fetch contacts: {e}")
        return

    from utils.validator import evaluate_contact_row
    from constants import COL_EMAIL, COL_FIRST_NAME, COL_VERIFIED, COL_STATUS, CampaignStatus
    from services.email_service import resolve_last_sent_info

    target_emails_clean = {e.strip().lower() for e in target_emails} if target_emails else None

    seen_emails = set()
    first_pending_contact = None
    for row in contacts:
        eval_res = evaluate_contact_row(row, seen_emails)
        status = str(row.get(COL_STATUS, "") or "").strip()
        is_already_sent = bool(resolve_last_sent_info(row)) or status in (CampaignStatus.SENT.value, CampaignStatus.FOLLOWUP_SENT.value)
        email_clean = str(row.get(COL_EMAIL, "") or "").strip().lower()

        if send_mode == SendMode.SELECTED.value:
            if eval_res["can_send"] and target_emails_clean and email_clean in target_emails_clean:
                first_pending_contact = row
                break
        elif send_mode == SendMode.RETRY_FAILED.value:
            if status == CampaignStatus.FAILED.value:
                first_pending_contact = row
                break
        elif send_mode == SendMode.RESEND_ONLY.value:
            if eval_res["can_send"] and is_already_sent:
                first_pending_contact = row
                break
        elif send_mode == SendMode.ALL_VERIFIED.value:
            if eval_res["can_send"]:
                first_pending_contact = row
                break
        else:
            if eval_res["can_send"] and not is_already_sent:
                first_pending_contact = row
                break

    if not first_pending_contact:
        # Fallback sample contact
        first_pending_contact = {
            COL_FIRST_NAME: "John",
            COL_EMAIL: "john.doe@example.com",
            COL_VERIFIED: "Yes",
        }
        st.info("No matching contacts found in database. Showing preview using a sample contact.")

    contact_email = first_pending_contact.get(COL_EMAIL, "")
    contact_name = first_pending_contact.get(COL_FIRST_NAME, "")

    st.write(f"📧 **Previewing for:** {contact_name} ({contact_email})")

    # Editable inputs for Subject and Body templates
    edited_subject = st.text_input("Subject Template", value=campaign.initial_subject)
    edited_body = st.text_area("Message Template Content", value=campaign.initial_body, height=180)

    # Rendered Preview
    st.markdown("**How it will look in their inbox:**")
    from services.email_service import render_template_string
    import streamlit.components.v1 as components

    sender_name = email_service.config_manager.settings.get("sender_name", "Mansi")
    signature = email_service.config_manager.settings.get("email_signature", "")

    context = email_service.build_context(first_pending_contact, sender_name)
    preview_subj = render_template_string(edited_subject, context)
    preview_body = render_template_string(edited_body, context)
    if signature and signature not in preview_body:
        preview_body = f"{preview_body}<br>{signature}"

    st.markdown(f"**Subject:** `{preview_subj}`")
    st.markdown(preview_body, unsafe_allow_html=True)

    st.write("Are you ready to start the campaign or do you want to keep editing?")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("🚀 Start Sending Now", type="primary", use_container_width=True):
            campaign.initial_subject = edited_subject
            campaign.initial_body = edited_body
            email_service.config_manager.update_campaign(campaign)

            st.session_state["execute_send_campaign"] = True
            st.session_state["send_mode"] = send_mode
            st.session_state["target_emails"] = target_emails
            st.rerun()
    with col2:
        if st.button("✏️ Save & Keep Editing", use_container_width=True):
            campaign.initial_subject = edited_subject
            campaign.initial_body = edited_body
            email_service.config_manager.update_campaign(campaign)
            st.toast("Draft templates saved successfully!", icon="💾")


@st.dialog("Warning: Emails Already Sent")
def confirm_resend_dialog(campaign, email_service, analysis):
    """
    Shown instead of jumping straight to the draft review when one or more verified
    contacts have already been sent this campaign's email at least once. Lets the user
    see how long it's been since each contact's last send and choose who to (re)send to.
    """
    already_sent = analysis["already_sent"]
    never_sent = analysis["never_sent"]

    st.write(
        f"**{len(already_sent)}** people have already received this email. "
        f"**{len(never_sent)}** people have not received it yet."
    )

    if already_sent:
        st.markdown("**Time since last send:**")
        preview_rows = [
            {
                "Email": c["email"],
                "First Name": c["first_name"],
                "Last Sent At": c["last_sent_at"],
                "Elapsed": format_elapsed(c["elapsed_seconds"]),
            }
            for c in already_sent
        ]
        st.dataframe(preview_rows, use_container_width=True, hide_index=True)

    st.write("Do you want to send the emails again? Choose who should receive this send:")

    mode_options = ["Only resend to people who already got it", "Send to everyone (including resending)"]
    mode_map = {
        "Only resend to people who already got it": SendMode.RESEND_ONLY.value,
        "Send to everyone (including resending)": SendMode.ALL_VERIFIED.value,
    }
    if never_sent:
        mode_options.insert(1, "Only send to new people who haven't received it")
        mode_map["Only send to new people who haven't received it"] = SendMode.NORMAL.value

    mode_label = st.radio("Who should we send to?", mode_options)
    chosen_mode = mode_map[mode_label]

    picker_rows = []
    for c in already_sent:
        picker_rows.append({
            "Send?": False,
            "Email": c["email"],
            "First Name": c["first_name"],
            "Status": "Already Sent",
            "Last Sent": f"{c['last_sent_at']} ({format_elapsed(c['elapsed_seconds'])} ago)",
        })
    for c in never_sent:
        picker_rows.append({
            "Send?": False,
            "Email": c["email"],
            "First Name": c["first_name"],
            "Status": "Never Sent",
            "Last Sent": "-",
        })

    with st.expander("🎯 Or pick specific people to email instead", expanded=False):
        st.caption(
            "Tick anyone you want to email, no matter which option you picked above. "
            "If you tick anyone here, only the ticked people will get the email."
        )
        picker_df = pd.DataFrame(picker_rows)
        edited_df = st.data_editor(
            picker_df,
            use_container_width=True,
            hide_index=True,
            disabled=["Email", "First Name", "Status", "Last Sent"],
            column_config={"Send?": st.column_config.CheckboxColumn("Send?")},
            key="resend_people_picker",
        )

    col_yes, col_no = st.columns(2)
    with col_yes:
        if st.button("Yes, Continue", type="primary", use_container_width=True):
            selected_emails = {
                row["Email"].strip().lower()
                for _, row in edited_df.iterrows()
                if row.get("Send?")
            } if picker_rows else set()

            if selected_emails:
                st.session_state["pending_send_mode"] = SendMode.SELECTED.value
                st.session_state["pending_target_emails"] = selected_emails
            else:
                st.session_state["pending_send_mode"] = chosen_mode
                st.session_state["pending_target_emails"] = None
            st.session_state["open_draft_review"] = True
            st.rerun()
    with col_no:
        if st.button("Cancel", use_container_width=True):
            st.rerun()
