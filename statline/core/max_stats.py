from __future__ import annotations

from typing import Any, Mapping, Optional, TypedDict

# -----------------------------------------------------------------------------
# Max-stats schema & defaults (source of truth if no remote sheet is provided)
# -----------------------------------------------------------------------------

class MaxStats(TypedDict):
    ppg: float
    apg: float
    orpg: float
    drpg: float
    spg: float
    bpg: float
    tov: float
    fgm: float
    fga: float


DEFAULT_MAX_STATS: MaxStats = {
    "ppg": 41.0,
    "apg": 18.0,
    "orpg": 7.0,
    "drpg": 8.0,
    "spg": 5.0,
    "bpg": 5.0,
    "tov": 8.0,
    "fgm": 16.0,
    "fga": 28.0,
}

# -----------------------------------------------------------------------------
# Remote resolver (optional Google Sheets). No filesystem access.
# -----------------------------------------------------------------------------

# Import lazily/optionally so strict type checkers are happy even without extras.
try:
    from statline.io.sheets import load_max_stats_from_sheets  # optional extra
except Exception:
    load_max_stats_from_sheets = None  # type: ignore[assignment]


def _merge_defaults(overrides: Mapping[str, Any]) -> MaxStats:
    """Overlay known keys from `overrides` onto defaults, coercing to float."""
    out: MaxStats = DEFAULT_MAX_STATS.copy()
    for k in out.keys():
        if k in overrides:
            try:
                out[k] = float(overrides[k])  # type: ignore[call-arg]
            except (TypeError, ValueError):
                # keep default if not coercible
                pass
    return out


def resolve_max_stats(
    *,
    spreadsheet_id: Optional[str] = None,
    worksheet_name: str = "MAX_STATS",
    credentials_file: Optional[str] = None,
) -> MaxStats:
    """
    Return max stats.

    - If `spreadsheet_id` is provided and Sheets extras are available, load from the
      given worksheet and merge onto defaults.
    - Otherwise, return a copy of DEFAULT_MAX_STATS.

    This function never touches local disk.
    """
    if spreadsheet_id and load_max_stats_from_sheets is not None:
        try:
            data = load_max_stats_from_sheets(
                spreadsheet_id=spreadsheet_id,
                worksheet_name=worksheet_name,
                credentials_file=credentials_file,
            )
            return _merge_defaults(data)
        except Exception:
            # Fail closed to safe defaults if remote read fails.
            return DEFAULT_MAX_STATS.copy()
    return DEFAULT_MAX_STATS.copy()
