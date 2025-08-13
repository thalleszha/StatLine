def clamp01(x):
    return max(0.0, min(1.0, x))

def norm(value, max_value):
    return clamp01(value / max_value) if max_value > 0 else 0.0

def get_input(prompt, cast_func=float, allow_empty=False, default=None):
    while True:
        try:
            val = input(prompt)
            if allow_empty and not val.strip():
                return default
            return cast_func(val)
        except ValueError:
            print("Invalid input, try again.")
