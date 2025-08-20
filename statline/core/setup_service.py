# statline/core/setup_service.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, Mapping, Optional

from .adapters import Adapter, load_adapter
from .db import get_conn
from .guild_manager import now_ts


@dataclass(frozen=True)
class SetupRequest:
    guild_id: str
    game_key: str                 # e.g., "rbw5", "valorant"
    sheet_key: str                # Google Sheets spreadsheet id
    sheet_tab: str = "MAX_STATS"  # worksheet/tab name
    # Optional league-level overrides (sparse; only keys you want to change)
    weights_override: Optional[Mapping[str, float]] = None
    caps_override: Optional[Mapping[str, float]] = None
    overwrite_overrides: bool = False


def _normalize_unit_weights(weights: Mapping[str, float]) -> Dict[str, float]:
    total = sum(abs(v) for v in weights.values())
    if total <= 0:
        raise ValueError("Weights must have non-zero total absolute magnitude.")
    return {k: (v / total) for k, v in weights.items()}


def _coerce_floats(m: Optional[Mapping[str, Any]]) -> Dict[str, float]:
    out: Dict[str, float] = {}
    if not m:
        return out
    for k, v in m.items():
        try:
            out[str(k)] = float(v)
        except (TypeError, ValueError):
            # skip invalid entries
            continue
    return out


def setup_league(req: SetupRequest) -> None:
    """
    Idempotent setup for a league (guild):
      - validate adapter and seed defaults for its metrics
      - upsert guild_config with sheet_key/sheet_tab/game_key
      - apply sparse per-league overrides for weights/caps
    """
    if not req.guild_id or not req.game_key or not req.sheet_key:
        raise ValueError("guild_id, game_key, and sheet_key are required.")

    # Load adapter (validated & cast inside load_adapter)
    adapter: Adapter = load_adapter(req.game_key)

    # Required surface from adapter
    metrics: Iterable[str] = getattr(adapter, "METRICS", ())
    if not metrics:
        raise RuntimeError(f"Adapter {req.game_key!r} does not expose METRICS.")

    # Adapter-provided defaults (optional)
    default_caps: Dict[str, float] = {}
    default_wts: Dict[str, float] = {}

    if hasattr(adapter, "DEFAULT_CAPS"):
        default_caps = {k: float(v) for k, v in getattr(adapter, "DEFAULT_CAPS").items()}
    if hasattr(adapter, "DEFAULT_WEIGHTS"):
        default_wts = {k: float(v) for k, v in getattr(adapter, "DEFAULT_WEIGHTS").items()}

    # Ensure coverage of all metrics; fill gaps with neutral defaults
    for m in metrics:
        default_caps.setdefault(m, 1.0)  # avoid div-by-zero
        default_wts.setdefault(m, 0.0)   # 0 weight = unused unless overridden

    # Normalize adapter weights if any non-zero present
    if any(v != 0.0 for v in default_wts.values()):
        default_wts = _normalize_unit_weights(default_wts)

    # League overrides (sparse)
    wt_override = _coerce_floats(req.weights_override)
    max_override = _coerce_floats(req.caps_override)
    if wt_override:
        wt_override = _normalize_unit_weights(wt_override)

    ts = now_ts()

    with get_conn() as conn:
        # 1) Register (or ensure) the game
        conn.execute(
            "INSERT INTO games (key, name) VALUES (?, ?) ON CONFLICT(key) DO NOTHING",
            (req.game_key, req.game_key.upper()),
        )

        # 2) Seed defaults for metrics (insert only; do not overwrite)
        rows = [
            (req.game_key, m, float(default_caps[m]), float(default_wts[m]), 0)
            for m in metrics
        ]
        conn.executemany(
            """
            INSERT INTO game_metrics (game_key, metric, default_max, default_wt, is_negative)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(game_key, metric) DO NOTHING
            """,
            rows,
        )

        # 3) Upsert guild_config
        conn.execute(
            """
            INSERT INTO guild_config (
                guild_id, sheet_key, sheet_tab, game_key,
                last_sync_ts, last_forced_update, rate_limit_day, created_ts, updated_ts
            )
            VALUES (?, ?, ?, ?, 0, 0, NULL, ?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET
                sheet_key = excluded.sheet_key,
                sheet_tab = excluded.sheet_tab,
                game_key  = excluded.game_key,
                updated_ts = excluded.updated_ts
            """,
            (req.guild_id, req.sheet_key, req.sheet_tab, req.game_key, ts, ts),
        )

        # 4) Apply per-league overrides
        if req.overwrite_overrides:
            conn.execute(
                "DELETE FROM league_metric_overrides WHERE guild_id = ?",
                (req.guild_id,),
            )

        for m, w in wt_override.items():
            if m in metrics:
                conn.execute(
                    """
                    INSERT INTO league_metric_overrides (guild_id, game_key, metric, wt_override)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(guild_id, metric) DO UPDATE SET wt_override = excluded.wt_override
                    """,
                    (req.guild_id, req.game_key, m, float(w)),
                )

        for m, cap in max_override.items():
            if m in metrics:
                conn.execute(
                    """
                    INSERT INTO league_metric_overrides (guild_id, game_key, metric, max_override)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(guild_id, metric) DO UPDATE SET max_override = excluded.max_override
                    """,
                    (req.guild_id, req.game_key, m, float(cap)),
                )
