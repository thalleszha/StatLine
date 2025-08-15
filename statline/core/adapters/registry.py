from __future__ import annotations
from pathlib import Path
from typing import Dict, List

from .loader import load_spec
from .compile import compile_adapter, CompiledAdapter  # must exist in compile.py

_CACHE: Dict[str, CompiledAdapter] = {}

def _discover() -> None:
    base = Path(__file__).parent / "defs"
    _CACHE.clear()
    # correct pattern: match .yaml or .yml
    for y in sorted(base.glob("*.y*ml")):
        spec = load_spec(y.stem)
        comp = compile_adapter(spec)
        # primary key
        _CACHE[comp.key.lower()] = comp
        # aliases
        for alias in comp.aliases:
            _CACHE[alias.lower()] = comp

def list_names() -> List[str]:
    if not _CACHE:
        _discover()
    # only primary keys (not aliases)
    return sorted({c.key for c in _CACHE.values()})

def load(name: str) -> CompiledAdapter:
    if not _CACHE:
        _discover()
    key = (name or "").lower()
    try:
        return _CACHE[key]
    except KeyError:
        raise ValueError(f"Unknown adapter '{name}'. Available: {', '.join(list_names())}")
