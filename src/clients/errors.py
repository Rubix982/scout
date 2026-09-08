# src/clients/errors.py
"""Turn gspread's masked exceptions back into actionable messages.

`gspread.Client.open_by_key` catches the informative `APIError` and re-raises a
bare `PermissionError`, discarding the message entirely. During setup that made
a *disabled Sheets API* read as "the sheet isn't shared" -- a wrong diagnosis
that cost real time. The underlying error is still reachable via `__cause__`, so
we recover it and say what actually happened.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import gspread


class SheetAccessError(RuntimeError):
    """Sheet could not be read, with a message that names the actual cause."""


def _api_error_payload(exc: BaseException) -> Optional[Dict[str, Any]]:
    """Dig the Google API error body out of an exception or its cause chain."""
    seen = 0
    cur: Optional[BaseException] = exc
    while cur is not None and seen < 5:
        if isinstance(cur, gspread.exceptions.APIError):
            response = getattr(cur, "response", None)
            if response is not None:
                try:
                    return response.json().get("error")
                except Exception:
                    return None
        cur = cur.__cause__ or cur.__context__
        seen += 1
    return None


def describe(exc: BaseException, *, sheet_url: str, service_account: str) -> str:
    """Build an actionable message for a failed sheet access."""
    if isinstance(exc, gspread.exceptions.WorksheetNotFound):
        return (
            f"Worksheet {exc!s} not found in the spreadsheet. Check the "
            f"worksheet name in secrets/gcp/common.env."
        )

    error = _api_error_payload(exc)
    if error is None:
        return f"{type(exc).__name__}: {exc}"

    status = error.get("status") or error.get("code")
    message = (error.get("message") or "").strip()
    reason = ""
    details = error.get("details") or []
    if details and isinstance(details[0], dict):
        reason = details[0].get("reason", "")
    if not reason:
        errs = error.get("errors") or []
        if errs and isinstance(errs[0], dict):
            reason = errs[0].get("reason", "")

    if reason in {"SERVICE_DISABLED", "accessNotConfigured"}:
        svc = ""
        if details and isinstance(details[0], dict):
            svc = (details[0].get("metadata") or {}).get("serviceTitle", "")
        return (
            f"A required Google API is not enabled on the project"
            + (f" ({svc})" if svc else "")
            + f". This is NOT a sharing problem. Enable it in the Cloud console, "
            f"wait a minute for propagation, and retry.\n  Google said: {message}"
        )

    if status in {"PERMISSION_DENIED", 403}:
        return (
            f"Permission denied reading the spreadsheet. Share it with the "
            f"service account as at least Viewer:\n"
            f"  {service_account}\n  Google said: {message}"
        )

    if status in {"NOT_FOUND", 404}:
        return (
            f"Spreadsheet not found. Check SHEET_URL in secrets/gcp/.env:\n"
            f"  {sheet_url}\n  Google said: {message}"
        )

    return f"Sheet access failed ({status}). Google said: {message}"
