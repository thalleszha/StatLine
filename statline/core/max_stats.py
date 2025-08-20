from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Mapping, TypedDict, cast


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
    "ppg": 41.0, "apg": 18.0, "orpg": 7.0, "drpg": 8.0,
    "spg": 5.0,  "bpg": 5.0,  "tov": 8.0,  "fgm": 16.0, "fga": 28.0,
}

MAX_STATS_FILE: Path = Path(
    os.getenv("STATLINE_MAX_STATS_FILE", Path.cwd() / "max_stats.json")
)

def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

def _normalize(d: Mapping[str, Any]) -> MaxStats:
    # Merge defaults and coerce to float; ignore extra keys
    base = cast(MaxStats, DEFAULT_MAX_STATS.copy())
    for k in DEFAULT_MAX_STATS.keys():
        if k in d:
            try:
                base[k] = float(d[k])  # type: ignore[arg-type]
            except (TypeError, ValueError):
                pass
    return base

def load_max_stats(path: Path = MAX_STATS_FILE) -> MaxStats:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return DEFAULT_MAX_STATS.copy()
        return _normalize(data)
    except FileNotFoundError:
        return DEFAULT_MAX_STATS.copy()
    except (json.JSONDecodeError, OSError):
        return DEFAULT_MAX_STATS.copy()

def save_max_stats(stats: MaxStats, path: Path = MAX_STATS_FILE) -> None:
    _ensure_parent(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=4)
    os.replace(tmp, path)
