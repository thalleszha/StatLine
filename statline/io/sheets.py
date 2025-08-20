# statline/io/sheets.py
from __future__ import annotations

import importlib
import os
from typing import Any, Optional, Protocol, cast, runtime_checkable


# ── minimal type surfaces so Pylance is happy without the extras installed ────
@runtime_checkable
class CredentialsClsProto(Protocol):
    @classmethod
    def from_service_account_file(cls, filename: str, *, scopes: list[str]) -> Any: ...

@runtime_checkable
class WorksheetProto(Protocol):
    def get_all_records(self) -> list[dict[str, Any]]: ...
    def get_all_values(self) -> list[list[str]]: ...

@runtime_checkable
class SpreadsheetProto(Protocol):
    def worksheet(self, title: str) -> WorksheetProto: ...

@runtime_checkable
class GSpreadClientProto(Protocol):
    def open_by_key(self, key: str) -> SpreadsheetProto: ...

@runtime_checkable
class GSpreadModuleProto(Protocol):
    def authorize(self, creds: Any) -> GSpreadClientProto: ...
    def service_account(self) -> GSpreadClientProto: ...
    def oauth(self) -> GSpreadClientProto: ...

# Optional runtime imports: available if user installs extras '.[sheets]'
gspread: Optional[GSpreadModuleProto]
Credentials: Optional[type[CredentialsClsProto]]

try:
    _gspread_mod = importlib.import_module("gspread")
    gspread = cast(GSpreadModuleProto, _gspread_mod)
    _google_sa = importlib.import_module("google.oauth2.service_account")
    Credentials = cast(Optional[type[CredentialsClsProto]], getattr(_google_sa, "Credentials", None))
except Exception:
    gspread = None
    Credentials = None

SHEETS_SCOPES: list[str] = ["https://www.googleapis.com/auth/spreadsheets.readonly"]


class SheetsNotInstalled(RuntimeError):
    def __init__(self) -> None:
        super().__init__(
            "Google Sheets support not installed. "
            "Install with: pip install '.[sheets]'"
        )


def _require_sheets() -> None:
    if gspread is None or Credentials is None:
        raise SheetsNotInstalled()


def get_gspread_client() -> GSpreadClientProto:
    """
    Prefer service-account auth via GOOGLE_APPLICATION_CREDENTIALS; fall back to
    gspread's helpers (service_account() / oauth()) when possible.

    Returns an authenticated gspread client or raises SheetsNotInstalled.
    """
    _require_sheets()
    assert gspread is not None and Credentials is not None  # type-narrowing

    creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if creds_path:
        creds = Credentials.from_service_account_file(creds_path, scopes=SHEETS_SCOPES)
        return gspread.authorize(creds)

    # Try gspread helpers (these look for local credentials)
    try:
        return gspread.service_account()
    except Exception:
        pass
    try:
        return gspread.oauth()
    except Exception:
        raise SheetsNotInstalled()


def fetch_rows_from_sheets(spreadsheet_id: str, worksheet_name: str) -> list[dict[str, Any]]:
    """
    Return rows as a list of dicts (header row → keys). Empty sheet → [].

    Raises SheetsNotInstalled if Sheets extras are missing.
    """
    client = get_gspread_client()
    ws: WorksheetProto = client.open_by_key(spreadsheet_id).worksheet(worksheet_name)
    rows = ws.get_all_records()
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
        creds = Credentials.from_service_account_file(credentials_path, scopes=SHEETS_SCOPES)
        client: GSpreadClientProto = gspread.authorize(creds)
    else:
        client = get_gspread_client()

    ws: WorksheetProto = client.open_by_key(spreadsheet_id).worksheet(worksheet_name)
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
