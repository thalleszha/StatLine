# statline/core/adapters/hooks.py
from __future__ import annotations

from typing import Any, Dict, Iterable, Protocol


class AdapterHooks(Protocol):
    # Called before mapping expressions run; can mutate/augment row
    def pre_map(self, row: Dict[str, Any]) -> Dict[str, Any]: ...

    # Called after mapping → metrics; can add derived metrics or fixups
    def post_map(self, metrics: Dict[str, float]) -> Dict[str, float]: ...

    # Optional format sniffing (CSV headers, etc.)
    def sniff(self, headers: Iterable[str]) -> bool: ...

# Default no-op implementation
class NoOpHooks:
    def pre_map(self, row: Dict[str, Any]) -> Dict[str, Any]:
        return row
    def post_map(self, metrics: Dict[str, float]) -> Dict[str, float]:
        return metrics
    def sniff(self, headers: Iterable[str]) -> bool:
        return False

# Simple registry for hook modules keyed by adapter key
_HOOKS: Dict[str, AdapterHooks] = {}

def register(key: str, hooks: AdapterHooks) -> None:
    _HOOKS[key.lower()] = hooks

def get(key: str) -> AdapterHooks:
    return _HOOKS.get(key.lower(), NoOpHooks())
