# statline/core/adapters/compile.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List

import re

from .types import AdapterSpec, MetricSpec, EffSpec
from .hooks import get as get_hooks

# Very small expression evaluator for mapping (safe, limited).
# Supports: $.field, $.a.b.c, + - * /, max(), min(), abs(), round()
_SAFE_FUNCS = {"max": max, "min": min, "abs": abs, "round": round}

# Regex to find tokens like $.foo or $.foo.bar.baz
_TOKEN = re.compile(r"\$\.(\w+(?:\.\w+)*)")


def _chain_get(root: str, chain: List[str]) -> str:
    """
    Build a safe chained dict-get expression.
    Example:
      root='row', chain=['a','b','c']
      -> "(row.get('a') if isinstance(row, dict) else None)"
         " and then successive .get(...) guarded by isinstance(...)"
    """
    # Start at the root
    expr = root
    # First hop: row.get('a') if row is dict else None
    first = chain[0]
    base = f"{expr}.get({first!r}) if isinstance({expr}, dict) else None"
    expr = f"({base})"
    # Subsequent hops: (<prev>.get('b') if isinstance(<prev>, dict) else None)
    for seg in chain[1:]:
        step = f"{expr}.get({seg!r}) if isinstance({expr}, dict) else None"
        expr = f"({step})"
    return expr


def _transform_expr(expr: str) -> str:
    """
    Replace all $.a.b.c tokens with safe chained dict-get code on 'row'.
    Leaves everything else as-is.
    """
    def repl(m: re.Match) -> str:
        chain = m.group(1).split(".")
        return _chain_get("row", chain)

    return _TOKEN.sub(repl, str(expr))


def _eval_expr(expr: str, row: Dict[str, Any]) -> float:
    """
    Evaluate adapter mapping expressions like:
      $.a + $.b
      $.fgm / max($.fga, 1)
    No builtins; only 'row', optional legacy 'raw', and _SAFE_FUNCS in scope.
    """
    code = _transform_expr(expr)

    # Globals: no builtins; Locals: row, legacy alias raw=row, and safe funcs
    globs: Dict[str, Any] = {"__builtins__": {}}
    locs: Dict[str, Any] = {"row": row, "raw": row, **_SAFE_FUNCS}

    val = eval(code, globs, locs)
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
