from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Mapping, cast

from statline.utils.config import DEFAULT_MAX_STATS, MaxStats

MAX_STATS_FILE = Path("max_stats.json")


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _normalize(data: Mapping[str, Any]) -> MaxStats:
    """
    Merge defaults with provided mapping and coerce values to float.
    Ignores unknown keys; invalid/missing values fall back to defaults.
    """
    # IMPORTANT: keep this as MaxStats, not dict[str, float]
    base: MaxStats = DEFAULT_MAX_STATS.copy()  # TypedDict-compatible copy
    for k in DEFAULT_MAX_STATS.keys():
        if k in data:
            try:
                base[k] = float(cast(Any, data[k]))
            except (TypeError, ValueError):
                pass
    return base


def load_max_stats(path: str | Path = MAX_STATS_FILE) -> MaxStats:
    p = Path(path)
    try:
        with p.open("r", encoding="utf-8") as f:
            obj = json.load(f)
        if isinstance(obj, dict):
            return _normalize(obj)
        return cast(MaxStats, DEFAULT_MAX_STATS.copy())
    except FileNotFoundError:
        return cast(MaxStats, DEFAULT_MAX_STATS.copy())
    except (json.JSONDecodeError, OSError):
        return cast(MaxStats, DEFAULT_MAX_STATS.copy())


def save_max_stats(stats: Mapping[str, float] | MaxStats, path: str | Path = MAX_STATS_FILE) -> None:
    p = Path(path)
    _ensure_parent(p)

    # Build a plain dict[str, float] in key order we expect (no type annotation needed)
    payload = {k: float(stats.get(k, DEFAULT_MAX_STATS[k]))  # type: ignore[index]
               for k in DEFAULT_MAX_STATS.keys()}

    tmp = p.with_suffix(p.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=4)
    os.replace(tmp, p)
