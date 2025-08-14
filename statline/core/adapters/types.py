from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

@dataclass(frozen=True)
class MetricSpec:
    key: str
    bucket: str
    clamp: Optional[Tuple[float, float]] = None
    invert: bool = False
    transform: Optional[str] = None

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
    aliases: Tuple[str, ...]
    title: str
    buckets: Dict[str, dict]
    metrics: List[MetricSpec]
    mapping: Dict[str, str]
    weights: Dict[str, Dict[str, float]]
    penalties: Dict[str, Dict[str, float]]
    efficiency: List[EffSpec] = field(default_factory=list)
