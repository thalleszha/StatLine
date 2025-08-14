# statline/core/adapters/__init__.py
from __future__ import annotations

import importlib
import pkgutil
from types import ModuleType
from typing import Protocol, Mapping, Any, Dict, Iterable, cast, runtime_checkable

# statline/adapters/__init__.py
# from . import rbw5   # when you add it
from .registry import list_names, load


# ──────────────────────────────────────────────────────────────────────────────
# Adapter contract (module-level Protocol)
# ──────────────────────────────────────────────────────────────────────────────

@runtime_checkable
class Adapter(Protocol):
    """
    Game adapter contract (implemented by a module).

    Required attrs on the module:
      KEY: str
      ALIASES: tuple[str, ...]
      METRICS: tuple[str, ...]
    Required callables:
      map_raw_to_metrics(raw: Mapping[str, Any]) -> dict[str, float]
      to_player_stats(raw: Mapping[str, Any]) -> Any
    Optional:
      sniff(headers: Iterable[str]) -> bool   # for auto-detect flows
    """
    KEY: str
    ALIASES: tuple[str, ...]
    METRICS: tuple[str, ...]

    def map_raw_to_metrics(self, raw: Mapping[str, Any]) -> dict[str, float]: ...
    def to_player_stats(self, raw: Mapping[str, Any]) -> Any: ...
    def sniff(self, headers: Iterable[str]) -> bool: ...  # type: ignore[empty-body]


# ──────────────────────────────────────────────────────────────────────────────
# Discovery & registry
# ──────────────────────────────────────────────────────────────────────────────

_PACKAGE = __name__  # "statline.core.adapters"
_DISCOVERED: Dict[str, str] = {}   # key/alias -> module path
_FROZEN = False


def _iter_adapter_modules() -> Iterable[str]:
    """Yield submodule paths under this package (one level)."""
    pkg = importlib.import_module(_PACKAGE)
    for _finder, name, ispkg in pkgutil.iter_modules(pkg.__path__):  # type: ignore[attr-defined]
        if not ispkg:
            yield f"{_PACKAGE}.{name}"


def _register_from_module(mod: ModuleType) -> None:
    key = getattr(mod, "KEY", None)
    metrics = getattr(mod, "METRICS", None)
    if not key or not isinstance(key, str) or not metrics:
        return  # not an adapter module
    _DISCOVERED[key.lower()] = mod.__name__
    aliases = getattr(mod, "ALIASES", ()) or ()
    if isinstance(aliases, (list, tuple)):
        for a in aliases:
            if isinstance(a, str) and a:
                _DISCOVERED[a.lower()] = mod.__name__


def _ensure_discovered() -> None:
    global _FROZEN
    if _FROZEN and _DISCOVERED:
        return
    _DISCOVERED.clear()
    for mod_name in _iter_adapter_modules():
        try:
            mod = importlib.import_module(mod_name)
            _register_from_module(mod)
        except Exception:
            # ignore broken modules during discovery
            continue
    _FROZEN = True


def supported_adapters() -> Dict[str, str]:
    """Return key/alias -> module path."""
    _ensure_discovered()
    return dict(_DISCOVERED)


def _validate_adapter_module(mod: ModuleType) -> Adapter:
    """Runtime-validate module surface, then cast so Pylance is happy."""
    for attr in ("KEY", "METRICS", "map_raw_to_metrics", "to_player_stats"):
        if not hasattr(mod, attr):
            raise RuntimeError(f"Module {mod.__name__} missing adapter attribute: {attr}")
    if not callable(getattr(mod, "map_raw_to_metrics")) or not callable(getattr(mod, "to_player_stats")):
        raise RuntimeError(f"Module {mod.__name__} adapter functions must be callable.")
    return cast(Adapter, mod)


def load_adapter(game_title: str) -> Adapter:
    """
    Load an adapter module by key or alias (case-insensitive).
    Example: adapter = load_adapter("rbw5")
    """
    _ensure_discovered()
    key = (game_title or "").strip().lower()
    mod_name = _DISCOVERED.get(key)
    if not mod_name:
        raise ValueError(f"Unsupported game adapter: {game_title!r}")
    mod = importlib.import_module(mod_name)
    return _validate_adapter_module(mod)


__all__ = ["Adapter", "supported_adapters", "load_adapter"]
