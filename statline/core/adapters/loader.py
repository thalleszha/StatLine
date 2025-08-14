from __future__ import annotations
from pathlib import Path
from typing import List, Dict, Any, Mapping
import yaml

from .types import AdapterSpec, MetricSpec, EffSpec

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

def load_spec(name: str) -> AdapterSpec:
    data = _read_yaml_for(name)

    # required keys
    for req in ("key", "version", "buckets", "metrics", "mapping"):
        if req not in data:
            raise KeyError(f"Adapter '{name}' is missing required key: {req}")

    metrics = [MetricSpec(**m) for m in data["metrics"]]
    effs: List[EffSpec] = [EffSpec(**e) for e in data.get("efficiency", [])]

    buckets = data["buckets"]
    weights = data.get("weights") or _uniform_weights(buckets)
    penalties = data.get("penalties", {})

    return AdapterSpec(
        key=data["key"],
        version=data["version"],
        aliases=tuple(data.get("aliases", [])),
        title=data.get("title", data["key"]),
        buckets=buckets,
        metrics=metrics,
        mapping=data["mapping"],
        weights=weights,
        penalties=penalties,
        efficiency=effs,
    )

# ──────────────────────────────────────────────────────────────
# Runtime wrapper so .map_raw() exists and eval has 'raw'
# ──────────────────────────────────────────────────────────────

def _translate_expr(expr: Any) -> str:
    """
    Accept both:
      - Pythonic:      raw["ppg"], ppg + apg*0.5, etc.
      - Legacy jq-ish: $.ppg, $.foo.bar  -> raw["foo"]["bar"]
    """
    s = str(expr)
    if s.startswith("$."):
        parts = s[2:].split(".")
        return "raw[" + "][".join(repr(p) for p in parts) + "]"
    return s

class Adapter:
    """Runtime adapter wrapper around an AdapterSpec, with safe mapping."""
    def __init__(self, spec: AdapterSpec):
        self.spec = spec
        self.key = spec.key
        self.metrics = spec.metrics
        self.weights = spec.weights
        self.mapping = spec.mapping
        self.buckets = spec.buckets
        self.penalties = spec.penalties
        self.efficiency = spec.efficiency

    def map_raw(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        # Build numeric context from declared metrics only
        ctx: Dict[str, Any] = {}
        for m in self.metrics:
            val = raw.get(m.key, 0)
            if isinstance(val, str):
                s = val.strip()
                if not s:
                    val = 0.0
                else:
                    try:
                        val = float(s.replace(",", "."))
                    except ValueError:
                        # leave as string if truly non-numeric
                        pass
            ctx[m.key] = val

        # Locals passed to eval: support both bare names (ppg) and raw["ppg"]
        eval_locals: Dict[str, Any] = dict(ctx)
        eval_locals["raw"] = ctx  # <- this fixes: name 'raw' is not defined

        mapped: Dict[str, Any] = {}
        for k, expr in self.mapping.items():
            code = _translate_expr(expr)
            try:
                mapped[k] = eval(code, {}, eval_locals)
            except SyntaxError as se:
                print(f"[Mapping SyntaxError] key={k!r}, expr={code!r}")
                print(f"Context: {eval_locals}")
                raise
            except Exception as e:
                print(f"[Mapping error] key={k!r}, expr={code!r}, error={e}")
                print(f"Context: {eval_locals}")
                raise
        return mapped

def load_adapter(name: str) -> Adapter:
    """Load a spec from YAML and wrap it in an Adapter with map_raw()."""
    spec = load_spec(name)
    return Adapter(spec)
