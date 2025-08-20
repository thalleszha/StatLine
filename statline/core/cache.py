from __future__ import annotations

from typing import Any, Dict, List, Optional

from .db import get_conn
from .guild_manager import (
    get_guild_config,
    iterate_guilds,
    now_ts,
    update_guild_config,
)
from .sheets_sync import sync_guild_sheets  # does real fetch+upsert into entities/metrics

# Default TTL: 24 hours
DEFAULT_SHEETS_TTL_SEC = 24 * 60 * 60


# ──────────────────────────────────────────────────────────────────────────────
# Freshness / TTL
# ──────────────────────────────────────────────────────────────────────────────

def _stale_since(last_sync_ts: Optional[int], ttl_sec: int) -> bool:
    if not last_sync_ts:
        return True
    return (now_ts() - int(last_sync_ts)) >= int(ttl_sec)


def should_sync_guild(guild_id: str, *, ttl_sec: int = DEFAULT_SHEETS_TTL_SEC) -> bool:
    """
    True if the guild's cache is stale and should be refreshed from Sheets.
    """
    cfg = get_guild_config(guild_id)
    if cfg is None:
        # Unconfigured guild -> nothing to sync
        return False
    return _stale_since(getattr(cfg, "last_sync_ts", None), ttl_sec)


def sync_guild_if_stale(
    guild_id: str,
    *,
    ttl_sec: int = DEFAULT_SHEETS_TTL_SEC,
    force: bool = False,
) -> int:
    """
    If due (or force=True), fetch from Sheets and upsert into DB.
    Returns: number of upserted rows (0 if skipped).
    On success, updates guild_config.last_sync_ts.
    """
    if not force and not should_sync_guild(guild_id, ttl_sec=ttl_sec):
        return 0

    upserted = int(sync_guild_sheets(guild_id) or 0)

    # Stamp freshness only on successful syncs (non-negative count)
    if upserted >= 0:
        update_guild_config(guild_id, last_sync_ts=now_ts())

    return upserted


def refresh_all_guilds(
    *,
    ttl_sec: int = DEFAULT_SHEETS_TTL_SEC,
    force: bool = False,
) -> Dict[str, int]:
    """
    Iterate all guilds and refresh stale ones.
    Returns a map of guild_id -> upserted count (or -1 on error).
    """
    results: Dict[str, int] = {}
    for gid in iterate_guilds():
        try:
            results[gid] = sync_guild_if_stale(gid, ttl_sec=ttl_sec, force=force)
        except Exception:
            # In production you'd log the exception
            results[gid] = -1
    return results


# ──────────────────────────────────────────────────────────────────────────────
# Adapter-agnostic reads from local cache
#   Schema:
#     entities(guild_id, fuzzy_key, display_name, group_name)
#     metrics(guild_id, fuzzy_key, metric_key, metric_value)
# ──────────────────────────────────────────────────────────────────────────────

def get_entities_for_guild(guild_id: str) -> List[Dict[str, Any]]:
    """
    Return all entities for a guild (adapter-agnostic).
    Sorted with non-null group_name first, then by group_name, then display_name.
    (SQLite has no 'NULLS LAST', so we emulate with IS NULL sort key.)
    """
    with get_conn() as conn:
        cur = conn.execute(
            """
            SELECT guild_id, fuzzy_key, display_name, group_name
            FROM entities
            WHERE guild_id = ?
            ORDER BY (group_name IS NULL) ASC, group_name ASC, display_name ASC
            """,
            (guild_id,),
        )
        return [dict(r) for r in cur.fetchall()]


def get_metrics_for_entity(guild_id: str, fuzzy_key: str) -> Dict[str, float]:
    """
    Return metric_key -> metric_value for one entity.
    """
    with get_conn() as conn:
        cur = conn.execute(
            """
            SELECT metric_key, metric_value
            FROM metrics
            WHERE guild_id = ? AND fuzzy_key = ?
            """,
            (guild_id, fuzzy_key),
        )
        return {row["metric_key"]: float(row["metric_value"]) for row in cur.fetchall()}


def get_metrics_for_guild(guild_id: str) -> List[Dict[str, Any]]:
    """
    Flattened view of all metrics for a guild:
      [{fuzzy_key, display_name, group_name, metric_key, metric_value}, ...]
    Useful for dumping to CSV or feeding a scorer in batch.
    """
    with get_conn() as conn:
        cur = conn.execute(
            """
            SELECT e.fuzzy_key,
                   e.display_name,
                   e.group_name,
                   m.metric_key,
                   m.metric_value
            FROM entities e
            JOIN metrics m
              ON e.guild_id = m.guild_id
             AND e.fuzzy_key = m.fuzzy_key
            WHERE e.guild_id = ?
            ORDER BY (e.group_name IS NULL) ASC, e.group_name ASC, e.display_name ASC, m.metric_key ASC
            """,
            (guild_id,),
        )
        return [dict(r) for r in cur.fetchall()]


def get_distinct_metric_keys(guild_id: str) -> List[str]:
    """
    List the unique metric keys present for this guild.
    Handy for building caps/contexts or a dynamic export header.
    """
    with get_conn() as conn:
        cur = conn.execute(
            """
            SELECT DISTINCT metric_key
            FROM metrics
            WHERE guild_id = ?
            ORDER BY metric_key ASC
            """,
            (guild_id,),
        )
        return [row["metric_key"] for row in cur.fetchall()]
