from __future__ import annotations

import time
from typing import Any, Iterator

from .db import get_conn
from .models import GuildConfig as GuildConfig

# Only these columns can be updated via update_guild_config
_ALLOWED_UPDATE_FIELDS: frozenset[str] = frozenset({
    "sheet_key",
    "sheet_tab",
    "rate_limit_day",
    "last_forced_update",
    "last_sync_ts",  # allow bumping sync timestamp too
})

def now_ts() -> int:
    return int(time.time())

# ──────────────────────────────────────────────────────────────────────────────
# Schema bootstrap + lightweight migrations (idempotent)
# ──────────────────────────────────────────────────────────────────────────────

def _table_has_column(table: str, col: str) -> bool:
    # xinfo includes hidden columns; more robust than table_info.
    with get_conn() as conn:
        cur = conn.execute(f"PRAGMA table_xinfo({table})")
        return any(row[1] == col for row in cur.fetchall())  # row[1] = name

def ensure_schema() -> None:
    """Create/upgrade the guild_config table."""
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS guild_config (
                guild_id TEXT PRIMARY KEY,
                sheet_key TEXT NOT NULL,
                sheet_tab TEXT NOT NULL DEFAULT 'STATS',
                rate_limit_day TEXT,
                last_forced_update INTEGER,
                last_sync_ts INTEGER,          -- freshness tracking
                created_ts INTEGER NOT NULL,
                updated_ts INTEGER NOT NULL
            )
            """
        )

    # Lightweight column migrations for existing installs
    if not _table_has_column("guild_config", "last_sync_ts"):
        with get_conn() as conn:
            conn.execute("ALTER TABLE guild_config ADD COLUMN last_sync_ts INTEGER")

# ──────────────────────────────────────────────────────────────────────────────
# CRUD
# ──────────────────────────────────────────────────────────────────────────────

def ensure_guild_entry(guild_id: str, sheet_key: str, sheet_tab: str = "STATS") -> None:
    ensure_schema()
    ts = now_ts()
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO guild_config (
                guild_id, sheet_key, sheet_tab, created_ts, updated_ts
            )
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET
                sheet_key = excluded.sheet_key,
                sheet_tab = excluded.sheet_tab,
                updated_ts = excluded.updated_ts
            """,
            (guild_id, sheet_key, sheet_tab, ts, ts),
        )

def get_guild_config(guild_id: str) -> GuildConfig | None:
    ensure_schema()
    with get_conn() as conn:
        cur = conn.execute(
            """
            SELECT
                guild_id,
                sheet_key,
                sheet_tab,
                last_sync_ts,
                rate_limit_day,
                last_forced_update,
                created_ts,
                updated_ts
            FROM guild_config
            WHERE guild_id = ?
            """,
            (guild_id,),
        )
        row = cur.fetchone()
        return GuildConfig.from_row(row) if row else None

def update_guild_config(
    guild_id: str,
    /,
    create_if_missing: bool = False,
    **fields: Any,
) -> None:
    if not fields:
        return

    bad = [k for k in fields if k not in _ALLOWED_UPDATE_FIELDS]
    if bad:
        raise ValueError(f"Disallowed field(s) in update_guild_config: {', '.join(bad)}")

    ts = now_ts()
    ordered = list(fields.items())
    set_clause = ", ".join(f"{k}=?" for k, _ in ordered)
    set_clause = f"{set_clause}, updated_ts=?"
    values = [v for _, v in ordered] + [ts, guild_id]

    ensure_schema()
    with get_conn() as conn:
        cur = conn.execute(
            f"UPDATE guild_config SET {set_clause} WHERE guild_id = ?",
            values,
        )
        if cur.rowcount == 0:
            if not create_if_missing:
                raise KeyError(f"guild_id '{guild_id}' not found")
            # Create minimal row, then apply update
            conn.execute(
                """
                INSERT INTO guild_config (guild_id, sheet_key, sheet_tab, created_ts, updated_ts)
                VALUES (?, ?, 'STATS', ?, ?)
                """,
                (guild_id, fields.get("sheet_key", ""), ts, ts),
            )
            # Re-apply the intended update (minus updated_ts which we’ll bump again)
            if ordered:
                values2 = [v for _, v in ordered] + [now_ts(), guild_id]
                conn.execute(
                    f"UPDATE guild_config SET {', '.join(f'{k}=?' for k, _ in ordered)}, updated_ts=? WHERE guild_id = ?",
                    values2,
                )

def iterate_guilds() -> Iterator[str]:
    ensure_schema()
    with get_conn() as conn:
        for (gid,) in conn.execute("SELECT guild_id FROM guild_config"):
            yield gid

def can_force_update_today(guild_id: str, today_str: str) -> bool:
    cfg = get_guild_config(guild_id)
    return not cfg or cfg.rate_limit_day != today_str

def set_forced_update_day(guild_id: str, today_str: str) -> None:
    update_guild_config(
        guild_id,
        rate_limit_day=today_str,
        last_forced_update=now_ts(),
    )

# ──────────────────────────────────────────────────────────────────────────────
# Convenience helpers
# ──────────────────────────────────────────────────────────────────────────────

def touch_last_sync(guild_id: str) -> None:
    """Set last_sync_ts=now and bump updated_ts."""
    update_guild_config(guild_id, last_sync_ts=now_ts())

def set_sheet_source(guild_id: str, *, key: str, tab: str = "STATS") -> None:
    """Update the Sheets source (key/tab) atomically."""
    update_guild_config(guild_id, sheet_key=key, sheet_tab=tab)

__all__ = [
    "GuildConfig",
    "now_ts",
    "ensure_schema",
    "ensure_guild_entry",
    "get_guild_config",
    "update_guild_config",
    "iterate_guilds",
    "can_force_update_today",
    "set_forced_update_day",
    "touch_last_sync",
    "set_sheet_source",
]