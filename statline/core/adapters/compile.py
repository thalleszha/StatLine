# statline/core/adapters/compile.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .types import AdapterSpec, MetricSpec, EffSpec
from .hooks import get as get_hooks

# Very small expression evaluator for mapping (safe, limited).
# Supports: $.field, + - * /, max(), min(), abs(), round()
_SAFE_FUNCS = {"max": max, "min": min, "abs": abs, "round": round}

def _eval_expr(expr: str, row: Dict[str, Any]) -> float:
    """
    Evaluate adapter mapping expressions like:
      $.a + $.b
      $.fgm / max($.fga, 1)
    No builtins; only 'row' and _SAFE_FUNCS in scope.
    """
    # Replace '$.foo' tokens with row['foo']
    # Keep expressions simple — this is intentionally minimal.
    transformed = expr.replace("$.", "row.get('")
    # Convert "row.get('foo.bar')" to "row.get('foo')['bar']"
    # naive but works for "a.b.c" chains:
    parts = []
    i = 0
    while i < len(transformed):
        if transformed.startswith("row.get('", i):
            j = transformed.find("')", i)
            if j != -1:
                key = transformed[i + 9:j]
                # split chains a.b.c into successive dict lookups
                chain = key.split(".")
                rep = f"row.get('{chain[0]}')"
                for seg in chain[1:]:
                    rep += f".get('{seg}') if isinstance({rep}, dict) else None"
                parts.append(rep)
                i = j + 2
                continue
        parts.append(transformed[i])
        i += 1
    code = "".join(parts)

    val = eval(code, {"__builtins__": {}}, {"row": row, **_SAFE_FUNCS})
    try:
        return float(0.0 if val is None else val)
    except (TypeError, ValueError):
        return 0.0

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
    mapping: Dict[str, str]                 # canonical key -> expr
    efficiency: List[EffSpec]               # optional make/attempt channels

    # --- API used by the scorer/CLI ---

    def eval_expr(self, expr: str, row: Dict[str, Any]) -> float:
        return _eval_expr(expr, row)

    def map_raw(self, raw: Dict[str, Any]) -> Dict[str, float]:
        """
        Apply mapping expressions to a raw row and produce canonical keys
        declared in self.metrics. Missing mappings default to 0.0.
        """
        hooks = get_hooks(self.key)
        row = hooks.pre_map(raw) if hasattr(hooks, "pre_map") else raw
        out: Dict[str, float] = {}
        for m in self.metrics:
            expr = self.mapping.get(m.key)
            if not expr:
                out[m.key] = 0.0
                continue
            val = self.eval_expr(expr, row)
            out[m.key] = float(val) if val is not None else 0.0
        # Allow post-map fixups
        return hooks.post_map(out) if hasattr(hooks, "post_map") else out

def compile_adapter(spec: AdapterSpec) -> CompiledAdapter:
    return CompiledAdapter(
        key=spec.key,
        version=spec.version,
        aliases=spec.aliases,
        title=spec.title,
        metrics=spec.metrics,
        buckets=spec.buckets,
        weights=spec.weights,
        penalties=spec.penalties,
        mapping=spec.mapping,
        efficiency=spec.efficiency,
    )
