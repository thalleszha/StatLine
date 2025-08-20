from __future__ import annotations

import math
from typing import Any, Callable, Optional, TypeVar, overload

T = TypeVar("T")

def clamp01(x: float) -> float:
    if isinstance(x, float):
        if math.isnan(x):
            return 0.0
        if math.isinf(x):
            return 1.0 if x > 0 else 0.0
    return max(0.0, min(1.0, float(x)))

def norm(value: float, max_value: float) -> float:
    if not value or not max_value:
        return 0.0
    if max_value <= 0 or math.isnan(value) or math.isnan(max_value):
        return 0.0
    try:
        return clamp01(float(value) / float(max_value))
    except ZeroDivisionError:
        return 0.0

@overload
def get_input(prompt: str, cast_func: type[int] = ..., allow_empty: bool = ..., default: Optional[int] = ...) -> Optional[int]: ...
@overload
def get_input(prompt: str, cast_func: type[float], allow_empty: bool = ..., default: Optional[float] = ...) -> Optional[float]: ...
@overload
def get_input(prompt: str, cast_func: type[str], allow_empty: bool = ..., default: Optional[str] = ...) -> Optional[str]: ...
@overload
def get_input(prompt: str, cast_func: Callable[[str], T], allow_empty: bool = ..., default: Optional[T] = ...) -> Optional[T]: ...

def get_input(
    prompt: str,
    cast_func: Callable[[str], Any] | type[Any] = float,
    allow_empty: bool = False,
    default: Optional[Any] = None,
) -> Optional[Any]:
    while True:
        try:
            raw_any = input(prompt)
        except (KeyboardInterrupt, EOFError):
            raise
        s = str(raw_any).strip()
        if allow_empty and not s:
            return default
        try:
            return cast_func(s)
        except (ValueError, TypeError):
            print("Invalid input, try again.")