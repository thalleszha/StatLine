# statline/io/sheets.py
from __future__ import annotations

import os
from typing import Optional

# Optional imports: available if user installs extras '.[sheets]'
try:
    import gspread  # type: ignore
    from google.oauth2.service_account import Credentials  # type: ignore
except Exception:  # ImportError or missing google-auth at dev time
    gspread = None
    Credentials = None  # type: ignore[assignment]

SHEETS_SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]


class SheetsNotInstalled(RuntimeError):
    def __init__(self) -> None:
        super().__init__(
            "Google Sheets support not installed. "
            "Install with: pip install '.[sheets]'"
        )


def _require_sheets() -> None:
    if gspread is None or Credentials is None:
        raise SheetsNotInstalled()


def get_gspread_client():
    """
    Prefer service-account auth via GOOGLE_APPLICATION_CREDENTIALS; fall back to
    gspread's helpers (service_account() / oauth()) when possible.

    Returns an authenticated gspread client or raises SheetsNotInstalled.
    """
    _require_sheets()
    # Let Pylance know these are not None beyond this point.
    assert gspread is not None and Credentials is not None

    # Try explicit service account via env var first
    creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if creds_path:
        creds = Credentials.from_service_account_file(  # type: ignore[reportOptionalMemberAccess]
            creds_path, scopes=SHEETS_SCOPES
        )
        return gspread.authorize(creds)  # type: ignore[reportOptionalMemberAccess]

    # Try gspread helpers (these look for local credentials)
    try:
        return gspread.service_account()  # type: ignore[attr-defined]
    except Exception:
        pass
    try:
        return gspread.oauth()  # type: ignore[attr-defined]
    except Exception:
        # If we got here, there is no viable auth path
        raise SheetsNotInstalled()


def fetch_rows_from_sheets(
    spreadsheet_id: str,
    worksheet_name: str,
) -> list[dict]:
    """
    Return rows as a list of dicts (header row → keys). Empty sheet → [].

    Raises SheetsNotInstalled if Sheets extras are missing.
    """
    client = get_gspread_client()
    ws = client.open_by_key(spreadsheet_id).worksheet(worksheet_name)
    rows = ws.get_all_records()  # header row => keys
    return rows or []


def load_max_stats_from_sheets(
    spreadsheet_id: str,
    worksheet_name: str = "MAX_STATS",
    credentials_file: Optional[str] = None,
) -> dict[str, float]:
    """
    Load MAX_STATS from a Google Sheet (two columns: key, value).

    Auth precedence:
      1) credentials_file param (service account JSON)
      2) GOOGLE_APPLICATION_CREDENTIALS env (service account JSON)
      3) get_gspread_client() fallback

    Requires extras: pip install '.[sheets]'
    """
    _require_sheets()
    assert gspread is not None and Credentials is not None

    credentials_path = credentials_file or os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if credentials_path:
        creds = Credentials.from_service_account_file(  # type: ignore[reportOptionalMemberAccess]
            credentials_path, scopes=SHEETS_SCOPES
        )
        client = gspread.authorize(creds)  # type: ignore[reportOptionalMemberAccess]
    else:
        client = get_gspread_client()

    ws = client.open_by_key(spreadsheet_id).worksheet(worksheet_name)
    rows = ws.get_all_values()

    out: dict[str, float] = {}
    for row in rows[1:] if rows else []:
        if len(row) >= 2:
            k = (row[0] or "").strip()
            v = (row[1] or "").strip()
            try:
                out[k] = float(v)
            except ValueError:
                # ignore non-numeric values
                pass
    return out
