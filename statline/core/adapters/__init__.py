# statline/core/adapters/__init__.py
from __future__ import annotations

import importlib
import pkgutil
from types import ModuleType
from typing import Any, Callable, Iterable, Mapping, Protocol, cast

# Re-export the public API expected by callers (e.g., `from statline.core.adapters import list_names, load`)
# If your canonical implementations live in .registry, keep this import.
# Otherwise, you can implement `list_names`/`load` here and drop the import.
from .registry import list_names, load  # noqa: F401  (re-exported via __all__)

# ──────────────────────────────────────────────────────────────────────────────
# Adapter contract (module-level Protocol)
# ──────────────────────────────────────────────────────────────────────────────

class Adapter(Protocol):
    """
    Describes the surface of an adapter *module*.

    Required module attributes:
      KEY: str
      ALIASES: tuple[str, ...]
      METRICS: tuple[str, ...]
      map_raw_to_metrics: Callable[[Mapping[str, Any]], dict[str, float]]
      to_player_stats: Callable[[Mapping[str, Any]], Any]

    Optional (not enforced by the Protocol):
      sniff: Callable[[Iterable[str]], bool]
    """

    KEY: str
    ALIASES: tuple[str, ...]
    METRICS: tuple[str, ...]
    map_raw_to_metrics: Callable[[Mapping[str, Any]], dict[str, float]]
    to_player_stats: Callable[[Mapping[str, Any]], Any]
    # NOTE: `sniff` is intentionally omitted from the Protocol so its absence
    #       doesn't violate typing. We still allow it at runtime.

# ──────────────────────────────────────────────────────────────────────────────
# Discovery & registry (runtime helper utilities)
# ──────────────────────────────────────────────────────────────────────────────

_PACKAGE = __name__  # "statline.core.adapters"
_DISCOVERED: dict[str, str] = {}   # key/alias -> module path
_FROZEN = False


def _iter_adapter_modules() -> Iterable[str]:
    """Yield submodule paths under this package (one level)."""
    pkg = importlib.import_module(_PACKAGE)
    # mypy: __path__ exists on packages at runtime; ignore for static analysis
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


def supported_adapters() -> dict[str, str]:
    """Return key/alias -> module path."""
    _ensure_discovered()
    return dict(_DISCOVERED)


def _validate_adapter_module(mod: ModuleType) -> Adapter:
    """Runtime-validate module surface, then cast so type checkers are satisfied."""
    required_attrs = ("KEY", "ALIASES", "METRICS", "map_raw_to_metrics", "to_player_stats")
    for attr in required_attrs:
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


__all__ = [
    # Public runtime helpers
    "Adapter",
    "supported_adapters",
    "load_adapter",
    # Explicit re-exports expected by import sites and mypy
    "list_names",
    "load",
]
