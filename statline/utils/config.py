from __future__ import annotations

from typing import Final, Mapping, TypedDict, cast

# ---- Scoring knobs (typed, immutable) ---------------------------------------

TEAM_WEIGHT: Final[float]     = 0.10     # how much team win% nudges score
TEAM_FACTOR_MIN: Final[float] = 0.95     # lower clamp on team factor
TEAM_FACTOR_MAX: Final[float] = 1.10     # upper clamp on team factor
M_SCALE: Final[float]         = 119.5    # linear map scale (pre-clamp)
M_OFFSET: Final[float]        = 4.1      # linear map offset (pre-clamp)

# ---- Max-stats shape --------------------------------------------------------

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

# Keep as a real dict so it's JSON-serializable and copyable;
# annotate as MaxStats so callers get key safety.
DEFAULT_MAX_STATS: MaxStats = {
    "ppg": 41.0, "apg": 18.0, "orpg": 7.0, "drpg": 8.0,
    "spg": 5.0,  "bpg": 5.0,  "tov": 8.0,  "fgm": 16.0, "fga": 28.0,
}

def default_max_stats_copy() -> MaxStats:
    """Return a mutable copy of the defaults (avoids accidental global mutation)."""
    return DEFAULT_MAX_STATS.copy()

def as_mapping(stats: MaxStats) -> Mapping[str, float]:
    """
    Help Pylance when passing a MaxStats to functions that want Mapping[str, float].
    Usage: calculate_scores_dc(..., max_stats=as_mapping(current_max))
    """
    return cast(Mapping[str, float], stats)

__all__ = [
    "TEAM_WEIGHT", "TEAM_FACTOR_MIN", "TEAM_FACTOR_MAX", "M_SCALE", "M_OFFSET",
    "MaxStats", "DEFAULT_MAX_STATS", "default_max_stats_copy", "as_mapping",
]
