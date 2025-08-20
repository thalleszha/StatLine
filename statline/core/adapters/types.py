from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Mapping, Optional, Tuple

# NOTE:
# - mapping is now OPTIONAL (default empty dict)
# - MetricSpec gains 'source' (strict schema) and 'transform' params (dict), both optional
# - aliases/penalties get sensible defaults

@dataclass(frozen=True)
class MetricSpec:
    key: str
    bucket: str
    clamp: Optional[Tuple[float, float]] = None
    invert: bool = False
    # STRICT SCHEMA FIELDS (optional for backward-compat with legacy adapters)
    source: Optional[Mapping[str, object]] = None   # e.g. {"field": "ppg"} or {"ratio": {...}}
    transform: Optional[Mapping[str, object]] = None  # e.g. {"name": "capped_linear", "params": {"cap": 300.0}}

@dataclass(frozen=True)
class EffSpec:
    key: str
    make: str
    attempt: str
    bucket: str
    transform: Optional[str] = None

@dataclass(frozen=True)
class AdapterSpec:
    key: str
    version: str
    aliases: Tuple[str, ...] = ()
    title: str = ""
    buckets: Dict[str, dict] = field(default_factory=dict)
    metrics: List[MetricSpec] = field(default_factory=list)
    # LEGACY: mapping expressions (optional)
    mapping: Dict[str, str] = field(default_factory=dict)
    weights: Dict[str, Dict[str, float]] = field(default_factory=dict)
    penalties: Dict[str, Dict[str, float]] = field(default_factory=dict)
    efficiency: List[EffSpec] = field(default_factory=list)
