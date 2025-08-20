# statline/core/adapters/__init__.py
from __future__ import annotations

import importlib
import pkgutil
from types import ModuleType
from typing import Any, Callable, Iterable, Mapping, Protocol, cast

from .registry import list_names, load  # re-exported via __all__

# ──────────────────────────────────────────────────────────────────────────────
# Adapter contract (module-level Protocol)
# ──────────────────────────────────────────────────────────────────────────────

class Adapter(Protocol):
    """Surface of an adapter *module*."""
    KEY: str
    ALIASES: tuple[str, ...]
    METRICS: tuple[str, ...]
    map_raw_to_metrics: Callable[[Mapping[str, Any]], dict[str, float]]
    to_player_stats: Callable[[Mapping[str, Any]], Any]
    # Optional at runtime: sniff(iterable_of_field_names) -> bool

# ──────────────────────────────────────────────────────────────────────────────
# Discovery & registry (runtime helper utilities)
# ──────────────────────────────────────────────────────────────────────────────

_PACKAGE = __name__  # "statline.core.adapters"
_DISCOVERED: dict[str, str] = {}   # key/alias -> module path
_frozen = False  # lower-case so reassignment doesn't trip "constant redefinition"


def _iter_adapter_modules() -> Iterable[str]:
    """Yield submodule paths under this package (one level)."""
    pkg = importlib.import_module(_PACKAGE)
    for _finder, name, ispkg in pkgutil.iter_modules(pkg.__path__):
        if not ispkg:
            yield f"{_PACKAGE}.{name}"

def _as_str_aliases(obj: object) -> tuple[str, ...]:
    """Materialize obj (tuple/list) into a tuple[str, ...], filtering non-strs."""
    if isinstance(obj, (list, tuple)):
        out: list[str] = []
        for e in cast(Iterable[object], obj):
            if isinstance(e, str) and e:
                out.append(e)
        return tuple(out)
    return ()


def _register_from_module(mod: ModuleType) -> None:
    key = getattr(mod, "KEY", None)
    metrics = getattr(mod, "METRICS", None)
    if not isinstance(key, str) or not key or metrics is None:
        return  # not an adapter module

    mod_name = mod.__name__
    _DISCOVERED[key.lower()] = mod_name

    aliases_raw: object = getattr(mod, "ALIASES", ()) or ()
    aliases_iter: tuple[str, ...] = _as_str_aliases(aliases_raw)

    for alias in aliases_iter:
        _DISCOVERED[alias.lower()] = mod_name


def _ensure_discovered() -> None:
    global _frozen
    if _frozen and _DISCOVERED:
        return
    _DISCOVERED.clear()
    for mod_name in _iter_adapter_modules():
        try:
            mod = importlib.import_module(mod_name)
            _register_from_module(mod)
        except Exception:
            # ignore broken modules during discovery
            continue
    _frozen = True


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
    "Adapter",
    "supported_adapters",
    "load_adapter",
    # Explicit re-exports expected by import sites and mypy
    "list_names",
    "load",
]
