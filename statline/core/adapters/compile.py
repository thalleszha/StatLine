# statline/core/adapters/compile.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, cast
import re
import math

from .types import AdapterSpec, MetricSpec, EffSpec
from .hooks import get as get_hooks

# ───────────────── Legacy mapping evaluator (safe, limited) ──────────────────

_SAFE_FUNCS = {"max": max, "min": min, "abs": abs, "round": round}
_TOKEN = re.compile(r"\$\.(\w+(?:\.\w+)*)")

def _chain_get(root: str, chain: List[str]) -> str:
    expr = root
    first = chain[0]
    base = f"{expr}.get({first!r}) if isinstance({expr}, dict) else None"
    expr = f"({base})"
    for seg in chain[1:]:
        step = f"{expr}.get({seg!r}) if isinstance({expr}, dict) else None"
        expr = f"({step})"
    return expr

def _transform_expr(expr: str) -> str:
    def repl(m: re.Match) -> str:
        chain = m.group(1).split(".")
        return _chain_get("row", chain)
    return _TOKEN.sub(repl, str(expr))

def _eval_expr(expr: str, row: Dict[str, Any]) -> float:
    """
    Evaluate legacy adapter mapping expressions with a tightly sandboxed eval:
      - Supports tokens like $.a.b.c via chained dict-get with isinstance checks
      - Exposes only minimal builtins required by generated code
      - Provides safe math helpers (max/min/abs/round) via locals
    """
    code = _transform_expr(expr)

    # Allow only what's needed by generated code (no full builtins exposure).
    safe_builtins: Dict[str, Any] = {
        "isinstance": isinstance,
        "dict": dict,
        # Uncomment if you ever reference these types directly in expressions:
        # "float": float,
        # "int": int,
    }
    globs: Dict[str, Any] = {"__builtins__": safe_builtins}
    locs: Dict[str, Any] = {"row": row, "raw": row, **_SAFE_FUNCS}

    val = eval(code, globs, locs)
    try:
        return float(0.0 if val is None else val)
    except (TypeError, ValueError):
        return 0.0

# ───────────────────── Strict-path helpers (no eval) ─────────────────────────

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
        return _num(row.get(src["field"], 0))
    if "ratio" in src:
        r = cast(Mapping[str, Any], src["ratio"])
        num = _num(row.get(r["num"], 0))
        den = _num(row.get(r["den"], 0))
        min_den = _num(r.get("min_den", 1))
        den = den if den >= max(min_den, 1e-12) else max(min_den, 1.0)
        return num / den
    if "sum" in src:
        return float(sum(_num(row.get(k, 0)) for k in cast(List[Any], src["sum"])))
    if "diff" in src:
        d = cast(Mapping[str, Any], src["diff"])
        return _num(row.get(d["a"], 0)) - _num(row.get(d["b"], 0))
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
        cap = _num(p["cap"]);  return x if x <= cap else cap
    if name == "minmax":
        lo, hi = _num(p["lo"]), _num(p["hi"]);  return min(max(x, lo), hi)
    if name == "pct01":
        by = _num(p.get("by", 100.0)) or 100.0;  return x / by
    if name == "softcap":
        cap, slope = _num(p["cap"]), _num(p["slope"]);  return x if x <= cap else cap + (x - cap) * slope
    if name == "log1p":
        return math.log1p(max(x, 0.0)) * _num(p.get("scale", 1.0))
    raise ValueError(f"Unknown transform '{name}'")

def _clamp(x: float, clamp: Optional[tuple[float, float]] | None) -> float:
    if not clamp:
        return x
    lo, hi = float(clamp[0]), float(clamp[1])
    return min(max(x, lo), hi)

# ────────────────────────── Compiled adapter ─────────────────────────────────

@dataclass(frozen=True)
class CompiledAdapter:
    key: str
    version: str
    aliases: tuple[str, ...]
    title: str
    metrics: List[MetricSpec]
    buckets: Dict[str, Any]
    weights: Dict[str, Dict[str, float]]
    penalties: Dict[str, Dict[str, float]]
    mapping: Dict[str, str]                 # legacy mapping (can be empty)
    efficiency: List[EffSpec]

    # --- API used by the scorer/CLI ---

    def eval_expr(self, expr: str, row: Dict[str, Any]) -> float:
        return _eval_expr(expr, row)

    def map_raw(self, raw: Dict[str, Any]) -> Dict[str, float]:
        """
        If legacy mapping exists → eval expressions safely.
        Else → compute from strict metric specs (source/transform/clamp).
        """
        hooks = get_hooks(self.key)
        row = hooks.pre_map(raw) if hasattr(hooks, "pre_map") else raw

        # Use entire sanitized row as context (legacy path needs arbitrary fields).
        ctx = _sanitize_row(row)

        # LEGACY PATH
        if self.mapping:
            out: Dict[str, float] = {}
            for m in self.metrics:
                expr = self.mapping.get(m.key)
                if not expr:
                    out[m.key] = 0.0
                    continue
                try:
                    val = _eval_expr(expr, ctx)
                except Exception as e:
                    print(f"[Mapping error] key={m.key!r}, expr={expr!r}: {e}")
                    val = 0.0
                out[m.key] = float(val)
            return hooks.post_map(out) if hasattr(hooks, "post_map") else out

        # STRICT PATH
        out: Dict[str, float] = {}
        for m in self.metrics:
            if m.source is None:
                raise KeyError(f"Metric '{m.key}' missing strict 'source' block (no legacy mapping present).")
            x = _compute_source(ctx, cast(Mapping[str, Any], m.source))
            x = _apply_transform(x, cast(Optional[Mapping[str, Any]], m.transform))
            x = _clamp(x, cast(Optional[tuple[float, float]], m.clamp))
            out[m.key] = float(x)
        return hooks.post_map(out) if hasattr(hooks, "post_map") else out

def compile_adapter(spec: AdapterSpec) -> CompiledAdapter:
    return CompiledAdapter(
        key=spec.key,
        version=spec.version,
        aliases=tuple(spec.aliases or ()),
        title=spec.title or spec.key,
        metrics=list(spec.metrics),
        buckets=dict(spec.buckets),
        weights=dict(spec.weights),
        penalties=dict(spec.penalties or {}),
        mapping=dict(spec.mapping or {}),
        efficiency=list(spec.efficiency or []),
    )
