# src/clients/gsuite.py
import os
from typing import List, Dict
import gspread
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv

# Constants
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]

# Load .env variables
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
GCP_SECRETS_DIR = os.path.join(PROJECT_ROOT, "secrets", "gcp")
GCP_COMMON_ENV_VAR_FILE = os.path.join(GCP_SECRETS_DIR, "common.env")
GCP_SECRETS_FILE = os.path.join(GCP_SECRETS_DIR, ".env")

# Validate secrets
for path in [GCP_COMMON_ENV_VAR_FILE, GCP_SECRETS_FILE]:
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Missing required env file: {path}")

# Load the .env file
load_dotenv(GCP_SECRETS_FILE)

SERVICE_ACCOUNT_FILENAME = os.getenv(
    "GCLOUD_SERVICE_ACCOUNT_FILENAME", "gcloud_service_account.json"
)
SERVICE_ACCOUNT_PATH = os.path.join(GCP_SECRETS_DIR, SERVICE_ACCOUNT_FILENAME)

if not os.path.isfile(SERVICE_ACCOUNT_PATH):
    raise FileNotFoundError(f"Missing service account file: {SERVICE_ACCOUNT_PATH}")


def get_gsheet_client() -> gspread.Client:
    credentials: Credentials = Credentials.from_service_account_file(
        SERVICE_ACCOUNT_PATH, scopes=SCOPES
    )
    return gspread.authorize(credentials)


def get_sheet_data(
    sheet_url: str, sheet_name: str
) -> List[Dict[str, int | float | str]]:
    client: gspread.Client = get_gsheet_client()
    worksheet: gspread.Worksheet = client.open_by_url(sheet_url).worksheet(sheet_name)
    return worksheet.get_all_records()


def get_processed_companies() -> List[Dict[str, int | float | str]]:
    sheet_url = os.getenv("SHEET_URL")
    sheet_name = os.getenv("PROCESSED_COMPANIES_SHEET_NAME", "Processed Companies")
    if not sheet_url:
        raise ValueError("SHEET_URL is not set in the environment.")
    return get_sheet_data(sheet_url, sheet_name)


def get_company_research() -> List[Dict[str, int | float | str]]:
    sheet_url = os.getenv("SHEET_URL")
    sheet_name = os.getenv("COMPANY_RESEARCH_SHEET_NAME", "Company Research")
    if not sheet_url:
        raise ValueError("SHEET_URL is not set in the environment.")
    return get_sheet_data(sheet_url, sheet_name)
