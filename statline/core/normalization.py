from __future__ import annotations

import math
from typing import Callable, Optional, TypeVar

T = TypeVar("T")

def clamp01(x: float) -> float:
    """
    Clamp a number to [0.0, 1.0].
    NaN -> 0.0; +/-inf -> 1.0/0.0 accordingly.
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
    if not isinstance(value, (int, float)) or not isinstance(max_value, (int, float)):
        return 0.0
    if max_value <= 0 or math.isnan(value) or math.isnan(max_value):
        return 0.0
    try:
        return clamp01(float(value) / float(max_value))
    except ZeroDivisionError:
        return 0.0

def get_input(
    prompt: str,
    cast_func: Callable[[str], T] = float,
    allow_empty: bool = False,
    default: Optional[T] = None,
) -> Optional[T]:
    """
    Prompt for input until conversion via cast_func succeeds.
    - If allow_empty and user enters only whitespace, return `default`.
    - Returns Optional[T] because `default` may be None.
    - Propagates KeyboardInterrupt / EOFError (Ctrl+C / Ctrl+D) so callers can exit cleanly.
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
            return cast_func(s)
        except (ValueError, TypeError):
            print("Invalid input, try again.")
