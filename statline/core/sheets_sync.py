# statline/services/sheets_sync.py
from __future__ import annotations

from typing import (
    TYPE_CHECKING,
    Any,
    Dict,
    Iterable,
    Mapping,
    Optional,
    Protocol,
    cast,
    runtime_checkable,
)

from statline.core.adapters import load_adapter, supported_adapters  # registry
from statline.core.db import get_conn

# Only import for types; mypy is happy and runtime stays clean
if TYPE_CHECKING:
    from statline.core.guild_manager import GuildConfig

from statline.core.guild_manager import get_guild_config, now_ts
from statline.io.sheets import fetch_rows_from_sheets

# ──────────────────────────────────────────────────────────────────────────────
# Adapter protocol(s): support either map_raw(...) or map_raw_to_metrics(...)
# ──────────────────────────────────────────────────────────────────────────────

@runtime_checkable
class _MapRawProto(Protocol):
    def map_raw(self, raw: Mapping[str, Any]) -> Dict[str, float]: ...


@runtime_checkable
class _MapRawToMetricsProto(Protocol):
    def map_raw_to_metrics(self, raw: Mapping[str, Any]) -> Dict[str, float]: ...


def _apply_adapter_map(adp: Any, raw: Mapping[str, Any]) -> Dict[str, float]:
    """Dispatch to whichever mapping function the adapter provides, with runtime type checks."""
    if isinstance(adp, _MapRawProto):
        return adp.map_raw(raw)
    if isinstance(adp, _MapRawToMetricsProto):
        return adp.map_raw_to_metrics(raw)
    raise AttributeError(f"Adapter {getattr(adp, 'KEY', adp)!r} lacks map_raw/map_raw_to_metrics")


# ──────────────────────────────────────────────────────────────────────────────
# Tiny utils
# ──────────────────────────────────────────────────────────────────────────────

def _normalize_str(v: Any) -> str:
    return str(v).strip()


def _fuzzy_key(name: str) -> str:
    return name.lower()


def _coerce_float(v: Any) -> Optional[float]:
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        s = v.strip()
        if not s:
            return None
        try:
            return float(s)
        except ValueError:
            return None
    return None


# ──────────────────────────────────────────────────────────────────────────────
# Schema for adapter-agnostic cache
# ──────────────────────────────────────────────────────────────────────────────

def _ensure_cache_schema() -> None:
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS entities (
                guild_id     TEXT NOT NULL,
                fuzzy_key    TEXT NOT NULL,
                display_name TEXT NOT NULL,
                group_name   TEXT,
                PRIMARY KEY (guild_id, fuzzy_key)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS metrics (
                guild_id     TEXT NOT NULL,
                fuzzy_key    TEXT NOT NULL,
                metric_key   TEXT NOT NULL,
                metric_value REAL NOT NULL DEFAULT 0,
                PRIMARY KEY (guild_id, fuzzy_key, metric_key),
                FOREIGN KEY (guild_id, fuzzy_key)
                    REFERENCES entities (guild_id, fuzzy_key)
                    ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_metrics_guild_metric ON metrics (guild_id, metric_key)"
        )


# ──────────────────────────────────────────────────────────────────────────────
# Adapter selection (optional sniff)
# ──────────────────────────────────────────────────────────────────────────────

def _autodetect_adapter(headers: Iterable[str]) -> Optional[str]:
    hdrs = [str(h).strip().lower() for h in headers]
    for key in sorted(supported_adapters().keys()):
        try:
            adp = load_adapter(key)
            sniff = getattr(adp, "sniff", None)
            if callable(sniff) and sniff(hdrs):
                return cast(str, getattr(adp, "KEY", key))
        except Exception:
            continue
    return None


# ──────────────────────────────────────────────────────────────────────────────
# Upserts
# ──────────────────────────────────────────────────────────────────────────────

def _upsert_entity(guild_id: str, display_name: str, group_name: Optional[str]) -> str:
    fuzzy = _fuzzy_key(display_name)
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO entities (guild_id, fuzzy_key, display_name, group_name)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(guild_id, fuzzy_key) DO UPDATE SET
                display_name = excluded.display_name,
                group_name   = excluded.group_name
            """,
            (guild_id, fuzzy, display_name, group_name),
        )
    return fuzzy


def _upsert_metrics(guild_id: str, fuzzy: str, mapped: Dict[str, Any]) -> int:
    rows: list[tuple[str, str, str, float]] = []
    for k, v in mapped.items():
        fv = _coerce_float(v)
        if fv is None:
            continue
        rows.append((guild_id, fuzzy, k, fv))
    if not rows:
        return 0
    with get_conn() as conn:
        conn.executemany(
            """
            INSERT INTO metrics (guild_id, fuzzy_key, metric_key, metric_value)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(guild_id, fuzzy_key, metric_key) DO UPDATE SET
                metric_value = excluded.metric_value
            """,
            rows,
        )
    return len(rows)


# ──────────────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────────────

def sync_guild_sheets(
    guild_id: str,
    *,
    adapter_key: Optional[str] = None,
    group_field_candidates: tuple[str, ...] = ("team", "group", "agent", "role"),
    name_field_candidates: tuple[str, ...] = ("display_name", "name", "player", "id"),
    cfg: GuildConfig | None = None,   # ✅ no quotes
) -> int:
    """
    Pull rows from Google Sheets and upsert into adapter-agnostic cache.
    """
    # compute cfg at call time (also makes it easy to inject a fixture in tests)
    cfg = cfg or get_guild_config(guild_id)
    if cfg is None or not cfg.sheet_key:
        raise RuntimeError("Guild is not configured. Set sheet_key/sheet_tab first.")

    rows = fetch_rows_from_sheets(cfg.sheet_key, cfg.sheet_tab or "STATS")

    if not rows:
        with get_conn() as conn:
            ts = now_ts()
            conn.execute(
                "UPDATE guild_config SET last_sync_ts = ?, updated_ts = ? WHERE guild_id = ?",
                (ts, ts, guild_id),
            )
        return 0

    headers = list(rows[0].keys())
    key = adapter_key or _autodetect_adapter(headers)
    if not key:
        raise RuntimeError("Unable to detect adapter for sheet; provide adapter_key explicitly.")

    adp = load_adapter(key)
    _ensure_cache_schema()

    upserted_entities = 0
    for raw in rows:
        display = ""
        for f in name_field_candidates:
            if f in raw and str(raw[f]).strip():
                display = _normalize_str(raw[f])
                break
        if not display:
            continue

        group_val: Optional[str] = None
        for f in group_field_candidates:
            if f in raw and str(raw[f]).strip():
                group_val = _normalize_str(raw[f]) 
                break

        mapped = _apply_adapter_map(adp, raw)
        fuzzy = _upsert_entity(guild_id, display, group_val)
        _upsert_metrics(guild_id, fuzzy, mapped)
        upserted_entities += 1

    with get_conn() as conn:
        ts = now_ts()
        conn.execute(
            "UPDATE guild_config SET last_sync_ts = ?, updated_ts = ? WHERE guild_id = ?",
            (ts, ts, guild_id),
        )

    return upserted_entities