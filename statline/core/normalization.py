from __future__ import annotations

import math
from typing import Any, Callable, Optional, TypeVar, overload

T = TypeVar("T")


def clamp01(x: float) -> float:
    """
    Clamp a number to [0.0, 1.0].
    NaN -> 0.0; +inf -> 1.0; -inf -> 0.0.
    """
    if isinstance(x, float):
        if math.isnan(x):
            return 0.0
        if math.isinf(x):
            return 1.0 if x > 0 else 0.0
    return max(0.0, min(1.0, float(x)))


def norm(value: float, max_value: float) -> float:
    """
    Normalize value by max_value into [0, 1].
    Returns 0.0 if max_value <= 0 or inputs are NaN.
    """
    if not value or not max_value:
        return 0.0
    if max_value <= 0 or math.isnan(value) or math.isnan(max_value):
        return 0.0
    try:
        return clamp01(float(value) / float(max_value))
    except ZeroDivisionError:
        return 0.0


# ── Typed overloads so the default `float` works and callers get precise types ──

@overload
def get_input(
    prompt: str,
    cast_func: type[int] = ...,
    allow_empty: bool = ...,
    default: Optional[int] = ...,
) -> Optional[int]: ...
@overload
def get_input(
    prompt: str,
    cast_func: type[float],
    allow_empty: bool = ...,
    default: Optional[float] = ...,
) -> Optional[float]: ...
@overload
def get_input(
    prompt: str,
    cast_func: type[str],
    allow_empty: bool = ...,
    default: Optional[str] = ...,
) -> Optional[str]: ...
@overload
def get_input(
    prompt: str,
    cast_func: Callable[[str], T],
    allow_empty: bool = ...,
    default: Optional[T] = ...,
) -> Optional[T]: ...


def get_input(
    prompt: str,
    cast_func: Callable[[str], Any] | type[Any] = float,
    allow_empty: bool = False,
    default: Optional[Any] = None,
) -> Optional[Any]:
    """
    Prompt for input until conversion via cast_func succeeds.

    - `cast_func` can be a callable (e.g., `lambda s: ...`) or a type like `int/float/str`.
    - If `allow_empty` and the user enters only whitespace, returns `default`.
    - Returns Optional[Any] here; overloads above give precise types to callers.
    - Propagates KeyboardInterrupt / EOFError so callers can exit cleanly.
    """
    while True:
        try:
            raw = input(prompt)
        except (KeyboardInterrupt, EOFError):
            # Let callers decide how to handle an interrupted prompt
            raise

        s = raw.strip()
        if allow_empty and not s:
            return default

        try:
            return cast_func(s)  # type: ignore[call-arg]  # acceptable: type[Any] is callable at runtime
        except (ValueError, TypeError):
            print("Invalid input, try again.")
