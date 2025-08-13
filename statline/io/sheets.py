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


def _require_sheets():
    if gspread is None or Credentials is None:
        raise SheetsNotInstalled()


def load_max_stats_from_sheets(
    spreadsheet_id: str,
    worksheet_name: str = "MAX_STATS",
    credentials_file: Optional[str] = None,
) -> dict[str, float]:
    """
    Load MAX_STATS from a Google Sheet (two columns: key, value).
    Requires extras: pip install '.[sheets]'

    Env fallback for credentials:
      GOOGLE_APPLICATION_CREDENTIALS=/path/to/service_account.json
    """
    _require_sheets()

    credentials_path = credentials_file or os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if not credentials_path:
        raise RuntimeError(
            "GOOGLE_APPLICATION_CREDENTIALS not set and no credentials_file provided."
        )

    creds = Credentials.from_service_account_file(credentials_path, scopes=SHEETS_SCOPES) # pyright: ignore[reportOptionalMemberAccess]
    client = gspread.authorize(creds) # pyright: ignore[reportOptionalMemberAccess]

    ws = client.open_by_key(spreadsheet_id).worksheet(worksheet_name)
    rows = ws.get_all_values()

    out: dict[str, float] = {}
    for row in rows[1:] if rows else []:
        if len(row) >= 2:
            k, v = row[0].strip(), row[1].strip()
            try:
                out[k] = float(v)
            except ValueError:
                # ignore non-numeric values
                pass
    return out
