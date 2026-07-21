# Automated Email Campaign Manager 📧

A production-grade Python application with a modern Streamlit GUI for personalizing and automating email campaigns using a **Google Sheet** as the single source of truth database and the **Gmail API** with OAuth 2.0 authentication.

---

## 🌟 Key Features

- **Google Sheet as Single Source of Truth**:
  - Automatically extracts 44-character Spreadsheet IDs from full Google Sheet URLs.
  - **Auto-Healing Schema**: Creates missing columns (`Email Sent Date`, `Follow-up Sent Date`, `Status`, `Last Error`, `Last Updated`, `Attempt Count`, `Next Follow-up Date`, `Gmail Message ID`, `Gmail Thread ID`) without touching user-owned columns like `Response Got`.
  - **Batching & Performance**: Queues row updates in memory and flushes every 20 rows to minimize Google Sheets API quota usage.
- **Gmail API & Conversation Threading**:
  - Sends HTML emails directly via official Gmail API (no SMTP, no Selenium).
  - **Gmail Threading**: Stores `Gmail Message ID` and `Gmail Thread ID` on initial send, ensuring follow-ups land inside the exact same email conversation thread in Gmail.
  - **Optional Draft Mode**: Option to generate Gmail Drafts for manual review instead of immediate sending.
- **Multi-Campaign Architecture**:
  - Manage multiple independent outreach campaigns with dedicated templates, sheets, and delay rules.
  - CRUD operations: Create, Edit, Duplicate, Archive, and Delete campaigns.
- **RFC-Compliant Email Validation**:
  - Integrated `email-validator` library checks syntax, domain structure, missing fields, duplicates, and verification flags.
- **Dynamic Jinja2 Templating & Live Preview**:
  - Variable support (`{{first_name}}`, `{{email}}`, `{{current_date}}`, `{{sender_name}}`, or custom sheet columns).
  - Live interactive HTML previewer with sample or real contact data.
- **Dry Run Analysis & Safety Controls**:
  - Simulates campaign runs and reports "Will Send", "Skipped (Reason)", "Invalid", and Estimated Duration.
  - Send Test Email functionality to verify rendered messages prior to launch.
- **Automated APScheduler Automation**:
  - Background cron scheduler for daily automated reads, sends, follow-ups, and sheet sync.
- **Comprehensive Analytics & Logging**:
  - Time-frame metrics (Today, Yesterday, Last 7 Days, Last 30 Days).
  - Live in-memory and file-rotated log viewer with level filtering and CSV exports.
  - Backup & restore settings JSON files.

---

## 📁 Project Structure

```
email_campaign_manager/
├── app.py                      # Main Streamlit application & navigation router
├── config.py                   # Global settings & multi-campaign JSON persistence manager
├── constants.py                # Status enums, column definitions, and system defaults
├── scheduler.py                # APScheduler background automation job runner
├── requirements.txt            # Dependency specifications
├── README.md                   # Setup guide and application documentation
│
├── data/                       # Local JSON persistence directory
│   ├── settings.json           # Global user preferences & sending parameters
│   └── campaigns.json          # Saved campaign configurations & templates
│
├── credentials/                # Google OAuth credentials
│   ├── client_secret.json      # User-supplied OAuth Client Secret (downloaded from GCP)
│   └── token.json              # Cached OAuth user token
│
├── logs/
│   └── campaign.log            # Rotated system activity log file
│
├── services/
│   ├── auth_service.py         # Google OAuth 2.0 flow & user profile manager
│   ├── sheets_service.py       # Google Sheets API client with batch updating & auto-healing
│   ├── email_provider.py       # Abstract `EmailProvider` interface
│   ├── gmail_provider.py       # `GmailProvider(EmailProvider)` with Threading & Draft mode
│   ├── email_service.py        # Dynamic rendering, dry run, and batch dispatcher engine
│   └── followup_service.py     # Automated follow-up candidate detection & thread reply builder
│
├── ui/
│   ├── dashboard.py            # Real-time health metrics, quick actions & activity feed
│   ├── campaigns.py            # Multi-campaign manager & state selector
│   ├── composer.py             # Template editor, live preview, test sender & dry run
│   ├── contacts.py             # Contact list explorer with search, status filters & CSV download
│   ├── analytics.py            # Time-framed performance stats and charts
│   ├── logs.py                 # Interactive log table & CSV downloader
│   └── settings.py             # Global preferences, OAuth status & backup import/export
│
├── templates/
│   ├── email_template.html     # Default initial email Jinja2 HTML template
│   └── followup_template.html  # Default follow-up email Jinja2 HTML template
│
└── utils/
    ├── validator.py            # Strict RFC email & row evaluator module
    └── logger.py               # Application logging utility & CSV log exporter
```

---

## 🛠️ Installation & Setup

### 1. Prerequisites
- **Python 3.12+** installed on your system.
- A **Google Account** with access to Google Cloud Console.

### 2. Installation Steps
Clone or navigate to the project directory and install required Python dependencies:

```bash
cd email_campaign_manager
pip install -r requirements.txt
```

---

## 🔑 Google Cloud Console Setup Guide

To connect the application to your Gmail account and Google Sheets, follow these one-time setup steps:

### Step 1: Create a Google Cloud Project
1. Go to the [Google Cloud Console](https://console.cloud.google.com/).
2. Click the project dropdown in the top bar and select **New Project**.
3. Name your project (e.g., `Email Campaign Manager`) and click **Create**.

### Step 2: Enable Required Google APIs
1. In the left navigation menu, go to **APIs & Services > Library**.
2. Search for **Gmail API**, select it, and click **Enable**.
3. Return to the Library, search for **Google Sheets API**, select it, and click **Enable**.

### Step 3: Configure OAuth Consent Screen
1. Go to **APIs & Services > OAuth consent screen**.
2. Select User Type **External** and click **Create**.
3. Fill in required App information (App name, User support email, Developer contact email).
4. Click **Save and Continue**.
5. Under **Scopes**, click **Add or Remove Scopes** and add:
   - `https://www.googleapis.com/auth/gmail.send`
   - `https://www.googleapis.com/auth/gmail.compose`
   - `https://www.googleapis.com/auth/gmail.readonly`
   - `https://www.googleapis.com/auth/spreadsheets`
6. Under **Test users**, add your own Gmail address (the email account you will send campaigns from).
7. Save and finish configuration.

### Step 4: Create OAuth 2.0 Credentials
1. Go to **APIs & Services > Credentials**.
2. Click **Create Credentials** > **OAuth client ID**.
3. Select **Application type**: **Desktop app**.
4. Set Name to `Desktop Client` and click **Create**.
5. Click **Download JSON** on the generated credentials popup.
6. Rename the downloaded file to `client_secret.json`.
7. Move `client_secret.json` into the `credentials/` directory of this project:
   `credentials/client_secret.json`

---

## 🚀 Running the Application

Launch the Streamlit web dashboard:

```bash
streamlit run app.py
```

The app will open automatically in your browser at `http://localhost:8501`.

---

## 📊 Google Sheet Data Format

Your Google Sheet should contain the following core columns:

| First Name | Email | Verified | Response Got |
| :--- | :--- | :--- | :--- |
| John | john.doe@example.com | Yes | |
| Alice | alice.smith@example.com | True | |

### Automatic Columns
When you sync or run a campaign, the application will automatically append missing system columns:
- `Email Sent Date`
- `Follow-up Sent Date`
- `Status`
- `Last Error`
- `Last Updated`
- `Attempt Count`
- `Next Follow-up Date`
- `Gmail Message ID`
- `Gmail Thread ID`

> [!IMPORTANT]
> The **Response Got** column is owned by you. Enter any text into this column when a contact replies to stop automatic follow-ups for that contact.

---

## ⏰ Background Scheduler Operation

The application includes an **APScheduler** background runner that can automatically read your Google Sheet, process pending initial emails, and send follow-ups daily at your designated time (e.g. 10:00 AM). You can toggle the scheduler on or off at any time from **Settings > Scheduler**.

---

## ❓ Troubleshooting

- **OAuth Authentication Failed**:
  - Ensure `credentials/client_secret.json` is present.
  - Verify your email is listed under **Test users** in Google Cloud Console.
  - If token expires, click **Connect Google** in the dashboard to re-authenticate.
- **Google Sheet Access Denied**:
  - Ensure your Google Sheet sharing settings allow access to your authenticated Google account.
- **Emails Not Sending**:
  - Check the **Logs** tab in the dashboard for exact error codes returned by Gmail API.

---

## 🔮 Future Improvements

- Add support for **Microsoft Outlook Graph API** and **Amazon SES** providers via the abstract `EmailProvider` interface.
- Add AI-assisted personalizer for customized message body generation per contact.
