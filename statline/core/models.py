from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, Mapping, Optional

# ──────────────────────────────────────────────────────────────────────────────
# Adapter-agnostic core models (for entities/metrics schema & PRI)
# ──────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Entity:
    guild_id: str
    fuzzy_key: str
    display_name: str
    group_name: Optional[str] = None

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "Entity":
        d = dict(row)
        return cls(
            guild_id=str(d["guild_id"]),
            fuzzy_key=str(d["fuzzy_key"]),
            display_name=str(d["display_name"]),
            group_name=(str(d["group_name"]) if d.get("group_name") is not None else None),
        )

@dataclass(frozen=True)
class MetricRow:
    guild_id: str
    fuzzy_key: str
    metric_key: str
    metric_value: float

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "MetricRow":
        d = dict(row)
        return cls(
            guild_id=str(d["guild_id"]),
            fuzzy_key=str(d["fuzzy_key"]),
            metric_key=str(d["metric_key"]),
            metric_value=float(d["metric_value"]),
        )

@dataclass(frozen=True)
class PriResult:
    """
    Generic PRI result used by adapter-agnostic scoring.
    - 'used_ratio' and 'aefg' remain optional to support legacy hoops extras.
    """
    score: float                      # final score, typically clamped [0..99]
    components: Dict[str, float]      # normalized per-metric contributions (0..1)
    weights: Dict[str, float]         # unit (L1) weights actually applied (sign-preserving)
    used_ratio: Optional[str] = None  # legacy: which TOV ratio was used
    aefg: Optional[float] = None      # legacy: raw approx eFG (not normalized)

# Back-compat alias: old code imports ScoreResult; keep it pointing to PriResult.
ScoreResult = PriResult

# ──────────────────────────────────────────────────────────────────────────────
# Configuration / guild state
# ──────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class GuildConfig:
    guild_id: str
    sheet_key: str
    sheet_tab: str = "STATS"                # neutral default
    last_sync_ts: int = 0
    rate_limit_day: Optional[str] = None
    last_forced_update: Optional[int] = None
    created_ts: int = 0
    updated_ts: int = 0

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "GuildConfig":
        d = dict(row)
        # tolerate missing/NULL fields
        return cls(
            guild_id=str(d["guild_id"]),
            sheet_key=str(d["sheet_key"]),
            sheet_tab=str(d.get("sheet_tab", "STATS")),
            last_sync_ts=int(d.get("last_sync_ts", 0) or 0),
            rate_limit_day=(str(d["rate_limit_day"]) if d.get("rate_limit_day") is not None else None),
            last_forced_update=(int(d["last_forced_update"]) if d.get("last_forced_update") is not None else None),
            created_ts=int(d.get("created_ts", 0) or 0),
            updated_ts=int(d.get("updated_ts", 0) or 0),
        )

# ──────────────────────────────────────────────────────────────────────────────
# Legacy hoops-specific models (kept for compatibility)
# ──────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class PlayerStats:
    """Legacy hoops-shaped stats. Adapters for other titles should not use this."""
    ppg: float
    apg: float
    orpg: float
    drpg: float
    spg: float
    bpg: float
    fgm: float
    fga: float
    tov: float

    @classmethod
    def from_mapping(cls, m: Mapping[str, Any]) -> "PlayerStats":
        def f(k: str) -> float:
            v = m[k]
            try:
                return float(v)
            except (TypeError, ValueError):
                raise ValueError(f"Invalid value for {k!r}: {v!r}")
        return cls(
            ppg=f("ppg"), apg=f("apg"), orpg=f("orpg"), drpg=f("drpg"),
            spg=f("spg"), bpg=f("bpg"), fgm=f("fgm"), fga=f("fga"), tov=f("tov"),
        )

    def as_dict(self) -> Dict[str, float]:
        return asdict(self)  # dict[str, float]

@dataclass(frozen=True)
class Team:
    id: int
    guild_id: str
    team_name: str
    wins: int = 0
    losses: int = 0

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "Team":
        d = dict(row)
        return cls(
            id=int(d["id"]),
            guild_id=str(d["guild_id"]),
            team_name=str(d["team_name"]),
            wins=int(d.get("wins", 0) or 0),
            losses=int(d.get("losses", 0) or 0),
        )

@dataclass(frozen=True)
class Player:
    id: int
    guild_id: str
    display_name: str
    fuzzy_key: str
    team_name: Optional[str]
    ppg: float
    apg: float
    orpg: float
    drpg: float
    spg: float
    bpg: float
    fgm: float
    fga: float
    tov: float

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "Player":
        d = dict(row)
        return cls(
            id=int(d["id"]),
            guild_id=str(d["guild_id"]),
            display_name=str(d["display_name"]),
            fuzzy_key=str(d["fuzzy_key"]),
            team_name=(str(d["team_name"]) if d.get("team_name") is not None else None),
            ppg=float(d.get("ppg", 0.0) or 0.0),
            apg=float(d.get("apg", 0.0) or 0.0),
            orpg=float(d.get("orpg", 0.0) or 0.0),
            drpg=float(d.get("drpg", 0.0) or 0.0),
            spg=float(d.get("spg", 0.0) or 0.0),
            bpg=float(d.get("bpg", 0.0) or 0.0),
            fgm=float(d.get("fgm", 0.0) or 0.0),
            fga=float(d.get("fga", 0.0) or 0.0),
            tov=float(d.get("tov", 0.0) or 0.0),
        )

__all__ = [
    # Adapter-agnostic
    "Entity",
    "MetricRow",
    "PriResult",
    "ScoreResult",   # alias to PriResult for back-compat
    "GuildConfig",
    # Legacy hoops
    "PlayerStats",
    "Team",
    "Player",
]
