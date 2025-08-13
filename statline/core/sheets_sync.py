from __future__ import annotations
from typing import Iterable, Dict, Any
from .guild_manager import get_guild_config, update_guild_config, now_ts
from .db import get_conn
# If you wire gspread, import lazily in a try/except inside the function.

def sync_guild_sheets(guild_id: str) -> int:
    """Pulls rows for guild from Google Sheets and upserts teams & players.
       Returns number of players updated."""
    cfg = get_guild_config(guild_id)
    if not cfg:
        raise RuntimeError("Guild is not configured. Run /setup first.")

    # TODO: fetch rows from Google Sheets using cfg["sheet_key"] / cfg["sheet_tab"]
    # For now, imagine we already parsed a list of players:
    players: Iterable[Dict[str, Any]] = []  # replace with real fetch

    conn = get_conn()
    count = 0
    with conn:
        for p in players:
            fuzzy = p["display_name"].strip().lower()
            conn.execute(
                """
                INSERT INTO players (guild_id, display_name, fuzzy_key, team_name,
                    ppg, apg, orpg, drpg, spg, bpg, fgm, fga, tov)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(guild_id, fuzzy_key) DO UPDATE SET
                    display_name=excluded.display_name,
                    team_name=excluded.team_name,
                    ppg=excluded.ppg, apg=excluded.apg, orpg=excluded.orpg, drpg=excluded.drpg,
                    spg=excluded.spg, bpg=excluded.bpg, fgm=excluded.fgm, fga=excluded.fga, tov=excluded.tov
                """,
                (guild_id, p["display_name"], fuzzy, p.get("team_name"),
                 p.get("ppg", 0), p.get("apg", 0), p.get("orpg", 0), p.get("drpg", 0),
                 p.get("spg", 0), p.get("bpg", 0), p.get("fgm", 0), p.get("fga", 0), p.get("tov", 0)),
            )
            count += 1

    update_guild_config(guild_id, last_sync_ts=now_ts())
    return count
