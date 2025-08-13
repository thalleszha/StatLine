from __future__ import annotations
import time
from typing import Optional, Dict, Any
from .db import get_conn

def now_ts() -> int:
    return int(time.time())

def ensure_guild_entry(guild_id: str, sheet_key: str, sheet_tab: str = "MAX_STATS") -> None:
    conn = get_conn()
    with conn:
        conn.execute(
            """
            INSERT INTO guild_config (guild_id, sheet_key, sheet_tab, created_ts, updated_ts)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET sheet_key=excluded.sheet_key,
                                               sheet_tab=excluded.sheet_tab,
                                               updated_ts=excluded.updated_ts
            """,
            (guild_id, sheet_key, sheet_tab, now_ts(), now_ts()),
        )

def get_guild_config(guild_id: str) -> Optional[Dict[str, Any]]:
    conn = get_conn()
    cur = conn.execute("SELECT * FROM guild_config WHERE guild_id=?", (guild_id,))
    row = cur.fetchone()
    return dict(row) if row else None

def update_guild_config(guild_id: str, **fields) -> None:
    if not fields:
        return
    keys = ", ".join([f"{k}=?" for k in fields.keys()])
    vals = list(fields.values()) + [guild_id]
    conn = get_conn()
    with conn:
        conn.execute(f"UPDATE guild_config SET {keys}, updated_ts=? WHERE guild_id=?", (*fields.values(), now_ts(), guild_id))

def iterate_guilds():
    conn = get_conn()
    cur = conn.execute("SELECT guild_id FROM guild_config")
    for (gid,) in cur.fetchall():
        yield gid

def can_force_update_today(guild_id: str, today_str: str) -> bool:
    cfg = get_guild_config(guild_id)
    return not cfg or cfg.get("rate_limit_day") != today_str

def set_forced_update_day(guild_id: str, today_str: str) -> None:
    update_guild_config(guild_id, rate_limit_day=today_str, last_forced_update=now_ts())
