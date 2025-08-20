# statline/core/adapters/compile.py
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from .hooks import get as get_hooks
from .types import AdapterSpec, EffSpec, MetricSpec

# ───────────────────── Strict-path helpers (no legacy / no eval) ─────────────

def _num(v: Any) -> float:
    try:
        if v is None:
            return 0.0
        if isinstance(v, (int, float)):
            return float(v)
        if isinstance(v, str):
            s = v.strip().replace(",", ".")
            return float(s) if s else 0.0
        return float(v)
    except Exception:
        return 0.0


def _sanitize_row(raw: Mapping[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for k, v in raw.items():
        if isinstance(v, str):
            s = v.strip()
            if s == "":
                out[str(k)] = 0.0
                continue
            try:
                out[str(k)] = float(s.replace(",", "."))
                continue
            except ValueError:
                pass
        out[str(k)] = v
    return out


def _compute_source(row: Mapping[str, Any], src: Mapping[str, Any]) -> float:
    if "field" in src:
        return _num(row.get(str(src["field"]), 0))

    if "ratio" in src:
        r = src["ratio"]
        num = _num(row.get(str(r["num"]), 0))
        den = _num(row.get(str(r["den"]), 0))
        min_den = _num(r.get("min_den", 1))
        den = den if den >= max(min_den, 1e-12) else max(min_den, 1.0)
        return num / den

    if "sum" in src:
        keys: Sequence[Any] = src["sum"]
        return float(sum(_num(row.get(str(k), 0)) for k in keys))

    if "diff" in src:
        d = src["diff"]
        return _num(row.get(str(d["a"]), 0)) - _num(row.get(str(d["b"]), 0))

    if "const" in src:
        return _num(src["const"])

    raise ValueError(f"Unsupported source: {src}")


def _apply_transform(x: float, spec: Optional[Mapping[str, Any]]) -> float:
    if not spec:
        return x
    name = str(spec.get("name", "")).lower()
    p = dict(spec.get("params") or {})
    if name == "linear":
        return x * _num(p.get("scale", 1.0)) + _num(p.get("offset", 0.0))
    if name == "capped_linear":
        cap = _num(p["cap"])
        return x if x <= cap else cap
    if name == "minmax":
        lo = _num(p["lo"])
        hi = _num(p["hi"])
        return min(max(x, lo), hi)
    if name == "pct01":
        by = _num(p.get("by", 100.0)) or 100.0
        return x / by
    if name == "softcap":
        cap = _num(p["cap"]) 
        slope = _num(p["slope"])
        return x if x <= cap else cap + (x - cap) * slope
    if name == "log1p":
        return math.log1p(max(x, 0.0)) * _num(p.get("scale", 1.0))
    raise ValueError(f"Unknown transform '{name}'")


def _clamp(x: float, clamp: Optional[Tuple[float, float]]) -> float:
    if not clamp:
        return x
    lo, hi = float(clamp[0]), float(clamp[1])
    return min(max(x, lo), hi)


# ────────────────────────── Compiled adapter (strict only) ───────────────────

@dataclass(frozen=True)
class CompiledAdapter:
    key: str
    version: str
    aliases: Tuple[str, ...]
    title: str
    metrics: List[MetricSpec]
    buckets: Dict[str, Any]
    weights: Dict[str, Dict[str, float]]
    penalties: Dict[str, Dict[str, float]]
    efficiency: List[EffSpec]

    def map_raw(self, raw: Dict[str, Any]) -> Dict[str, float]:
        """
        Compute metrics from strict specs (source/transform/clamp).
        Legacy expression mapping is not supported.
        """
        hooks = get_hooks(self.key)
        row = hooks.pre_map(raw) if hasattr(hooks, "pre_map") else raw
        ctx = _sanitize_row(row)

        out: Dict[str, float] = {}
        for m in self.metrics:
            if m.source is None:
                raise KeyError(
                    f"Metric '{m.key}' missing strict 'source' block "
                    f"(legacy mapping is unsupported)."
                )
            x = _compute_source(ctx, m.source)
            x = _apply_transform(x, m.transform)
            x = _clamp(x, m.clamp)
            out[m.key] = float(x)

        return hooks.post_map(out) if hasattr(hooks, "post_map") else out


def compile_adapter(spec: AdapterSpec) -> CompiledAdapter:
    # Enforce strict mode: refuse legacy mapping
    if getattr(spec, "mapping", None):
        raise ValueError(
            "Legacy expression mapping is no longer supported. "
            "Convert adapter to strict 'source/transform/clamp' spec."
        )

    # Use annotated locals to pin concrete types and silence “partially unknown”.
    metrics: List[MetricSpec] = list(spec.metrics)
    buckets: Dict[str, Any] = dict(spec.buckets or {})
    weights: Dict[str, Dict[str, float]] = dict(spec.weights or {})
    penalties: Dict[str, Dict[str, float]] = dict(spec.penalties or {})
    efficiency: List[EffSpec] = list(spec.efficiency or [])

    return CompiledAdapter(
        key=spec.key,
        version=spec.version,
        aliases=tuple(spec.aliases or ()),
        title=(spec.title or spec.key),
        metrics=metrics,
        buckets=buckets,
        weights=weights,
        penalties=penalties,
        efficiency=efficiency,
    )
