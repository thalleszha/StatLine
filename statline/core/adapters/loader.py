from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple, cast

import yaml

from .types import AdapterSpec, EffSpec, MetricSpec

_BASE = Path(__file__).parent / "defs"

def _read_yaml_for(name: str) -> dict:
    p = _BASE / f"{name}.yaml"
    if not p.exists():
        p = _BASE / f"{name}.yml"
    if not p.exists():
        raise FileNotFoundError(f"Adapter spec not found: {name}")
    return yaml.safe_load(p.read_text(encoding="utf-8")) or {}

def _uniform_weights(buckets: Dict[str, dict]) -> Dict[str, Dict[str, float]]:
    keys = list(buckets.keys())
    n = len(keys) or 1
    w = 1.0 / n
    return {"pri": {k: w for k in keys}}

def _as_clamp(v: Any) -> Optional[Tuple[float, float]]:
    if not v:
        return None
    a, b = v[0], v[1]
    return (float(a), float(b))

def load_spec(name: str) -> AdapterSpec:
    data = _read_yaml_for(name)

    # Required keys (mapping is OPTIONAL now)
    for req in ("key", "version", "buckets", "metrics"):
        if req not in data:
            raise KeyError(f"Adapter '{name}' is missing required key: {req}")

    # Buckets and weights
    buckets: Dict[str, dict] = cast(Dict[str, dict], data["buckets"])
    weights: Dict[str, Dict[str, float]] = cast(
        Dict[str, Dict[str, float]],
        data.get("weights") or _uniform_weights(buckets),
    )
    penalties: Dict[str, Dict[str, float]] = cast(Dict[str, Dict[str, float]], data.get("penalties", {}))

    # Metrics — support strict schema fields
    metrics: List[MetricSpec] = []
    for m in cast(List[Mapping[str, Any]], data["metrics"]):
        metrics.append(
            MetricSpec(
                key=str(m["key"]),
                bucket=str(m["bucket"]),
                clamp=_as_clamp(m.get("clamp")),
                invert=bool(m.get("invert", False)),
                source=cast(Optional[Mapping[str, Any]], m.get("source")),
                transform=cast(Optional[Mapping[str, Any]], m.get("transform")),
            )
        )

    # Efficiency (pass-through if you use it)
    eff_list: List[EffSpec] = []
    for e in cast(List[Mapping[str, Any]], data.get("efficiency", [])):
        eff_list.append(
            EffSpec(
                key=str(e["key"]),
                make=str(e["make"]),
                attempt=str(e["attempt"]),
                bucket=str(e["bucket"]),
                transform=cast(Optional[str], e.get("transform")),
            )
        )

    # Optional legacy mapping (keep for backward compat)
    mapping: Dict[str, str] = cast(Dict[str, str], data.get("mapping", {}))

    return AdapterSpec(
        key=str(data["key"]),
        version=str(data["version"]),
        aliases=tuple(data.get("aliases", [])),
        title=str(data.get("title", data["key"])),
        buckets=buckets,
        metrics=metrics,
        mapping=mapping,           # may be empty {}
        weights=weights,
        penalties=penalties,
        efficiency=eff_list,
    )
