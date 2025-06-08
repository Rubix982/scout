# 🔐 Google Sheets Authentication Guide

This guide walks you through how to **connect your Python tool to Google Sheets** using a **Service Account** and securely pull data from specific worksheets.

## Table Of Contents

- [🔐 Google Sheets Authentication Guide](#-google-sheets-authentication-guide)
  - [Table Of Contents](#table-of-contents)
  - [📦 Prerequisites](#-prerequisites)
  - [✅ Step 1: Enable Google APIs](#-step-1-enable-google-apis)
  - [🛠️ Step 2: Create a Service Account](#️-step-2-create-a-service-account)
  - [🔒 Step 3: Share Your Google Sheet](#-step-3-share-your-google-sheet)
  - [💻 Step 4: Install Required Python Packages](#-step-4-install-required-python-packages)
  - [🔁 Step 5: Authenticate in Code](#-step-5-authenticate-in-code)
  - [🧪 Example Usage](#-example-usage)
  - [🔐 Security Note](#-security-note)

## 📦 Prerequisites

- Google Account
- Access to [Google Cloud Console](https://console.cloud.google.com/)
- Python installed with `pip`

---

## ✅ Step 1: Enable Google APIs

1. Visit: [Google Cloud Console](https://console.cloud.google.com/)
2. Create or select an existing project.
3. Go to **APIs & Services → Library**
4. Enable the following APIs:
   - **Google Sheets API**
   - **Google Drive API**

---

## 🛠️ Step 2: Create a Service Account

1. Go to **APIs & Services → Credentials**
2. Click **Create Credentials → Service Account**
3. Name it something like `scout-sheets-reader`
4. Grant no additional roles (read-only is enough)
5. Click **Done**
6. In the service account list, click on the one you just created
7. Go to **Keys → Add Key → Create new key**
8. Choose **JSON**
9. Download the file and place it in your project folder (e.g., `secrets/gcloud_service_account.json`)

---

## 🔒 Step 3: Share Your Google Sheet

1. Open the Google Sheet you want to use.
2. Click **Share**
3. Paste the **service account email** (e.g. `scout-sheets-reader@scout-xxxxxx.iam.gserviceaccount.com`)
4. Give it **Viewer access**.
5. Save.

---

## 💻 Step 4: Install Required Python Packages

```bash
pip install gspread google-auth
````

---

## 🔁 Step 5: Authenticate in Code

Here's a minimal working example to read a worksheet:

```python
import gspread
from google.oauth2.service_account import Credentials

SERVICE_ACCOUNT_FILE = "secrets/gcloud_service_account.json"
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]

def get_gsheet_client():
    credentials = Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE,
        scopes=SCOPES
    )
    return gspread.authorize(credentials)

def get_sheet_data(sheet_url: str, sheet_name: str):
    client = get_gsheet_client()
    sheet = client.open_by_url(sheet_url)
    worksheet = sheet.worksheet(sheet_name)
    return worksheet.get_all_records()
```

---

## 🧪 Example Usage

```python
sheet_url = "https://docs.google.com/spreadsheets/d/your_spreadsheet_id_here/edit"
data = get_sheet_data(sheet_url, "Processed Companies")

for row in data:
    print(row["company"], row["tags"])
```

---

## 🔐 Security Note

* **Never commit** your service account JSON key to version control.
* Add this to `.gitignore`:

```bash
secrets/gcloud_service_account.json
```
