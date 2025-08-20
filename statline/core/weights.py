# statline/core/weights.py
from __future__ import annotations

from typing import Dict, Iterable, Mapping, Optional, SupportsFloat


def normalize_weights(weights: Mapping[str, SupportsFloat]) -> dict[str, float]:
    """
    Normalize weights (ints/floats) so their L1 (sum of absolute values) is 1.0.
    Preserves sign (so you can penalize 'bad' metrics with negative weights).
    If all weights are zero/missing, returns {}.
    """
    total = float(sum(abs(float(v)) for v in weights.values()))
    if total <= 0.0:
        return {}
    return {k: float(v) / total for k, v in weights.items()}


def resolve_weights(
    metrics: Iterable[str],
    *,
    defaults: Optional[Mapping[str, SupportsFloat]] = None,
    override: Optional[Mapping[str, SupportsFloat]] = None,
    fill_missing_with_zero: bool = True,
) -> dict[str, float]:
    """
    Merge default weights with league overrides (override wins), then normalize.

    - `metrics`: canonical metric keys for the current adapter (whatever it emits).
    - `defaults`: adapter-provided weights (optional).
    - `override`: league- or guild-specific overrides (sparse, optional).
    - `fill_missing_with_zero`: if True, any metric not present gets 0 weight.

    Returns unit (L1) weights; may be empty if everything is zero.
    """
    merged: Dict[str, float] = {}

    # Start from defaults
    if defaults:
        for k, v in defaults.items():
            merged[str(k)] = float(v)

    # Apply overrides
    if override:
        for k, v in override.items():
            merged[str(k)] = float(v)

    # Ensure only known metrics remain; optionally fill missing with zeros
    metric_set = set(metrics)
    merged = {k: v for k, v in merged.items() if k in metric_set}
    if fill_missing_with_zero:
        for m in metric_set:
            merged.setdefault(m, 0.0)

    return normalize_weights(merged)


def pick_profile(
    profiles: Mapping[str, Mapping[str, SupportsFloat]] | None,
    name: str | None,
) -> Mapping[str, SupportsFloat]:
    """
    If an adapter exposes multiple weight profiles (e.g., 'default', 'mvp', 'defense'),
    select one by name; fall back to 'default' or empty mapping.
    """
    if not profiles:
        return {}
    if name and name in profiles:
        return profiles[name]
    if "default" in profiles:
        return profiles["default"]
    # just grab the first profile deterministically
    first_key = next(iter(profiles.keys()))
    return profiles[first_key]
