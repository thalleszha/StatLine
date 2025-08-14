from __future__ import annotations

from typing import Dict, Any, List, Optional, Mapping, Callable, IO, cast, Iterable
import typer

from .adapters import list_names, load as load_adapter
from .scoring import calculate_pri

app = typer.Typer(no_args_is_help=True)

# ──────────────────────────────────────────────────────────────────────────────
# Input helpers
# ──────────────────────────────────────────────────────────────────────────────

def safe_map_raw(adapter, raw_metrics: Dict[str, Any]) -> Dict[str, Any]:
    """
    Wrap adapter.map_raw() with input sanitation and SyntaxError debugging.
    Ensures only numeric metrics get passed into eval paths.
    """
    # Strip and coerce numeric metrics
    numeric_metrics = {}
    for k, v in raw_metrics.items():
        if isinstance(v, str):
            v = v.strip()
            try:
                v = float(v) if v else 0.0
            except ValueError:
                # Keep non-numeric metrics as-is (e.g., display_name)
                pass
        numeric_metrics[k] = v

    try:
        mapped_any = adapter.map_raw(numeric_metrics)
        return dict(mapped_any)
    except SyntaxError as se:
        print("\n=== Mapping Syntax Error ===")
        print(f"Error: {se}")
        print("Raw metrics (sanitized):", numeric_metrics)
        # If adapter has an eval_expr or similar, dump it
        eval_expr = getattr(adapter, "eval_expr", None)
        if eval_expr:
            print("Eval expression:", eval_expr)
        print("============================\n")
        raise


def _prompt_float_strict(name: str) -> float:
    """
    Prompt until a valid float is entered. Supports comma decimals.
    Empty input => 0.0.
    """
    while True:
        s = input(f"{name}: ").strip()
        if not s:
            return 0.0
        try:
            return float(s.replace(",", "."))
        except ValueError:
            print("  Enter a number (e.g., 0.7) or leave blank for 0.")

def _get_mapper(adapter: Any) -> Callable[[Mapping[str, Any]], Mapping[str, Any]]:
    """
    Return the adapter's mapping function with a tolerant signature so Pylance
    doesn't complain (adapters vary). Prefer map_raw, else map_raw_to_metrics.
    """
    fn: Any = getattr(adapter, "map_raw", None)
    if not callable(fn):
        fn = getattr(adapter, "map_raw_to_metrics", None)
    if not callable(fn):
        raise RuntimeError("Adapter has neither map_raw nor map_raw_to_metrics")
    # Keep it untyped (Any) to avoid attribute errors; we wrap its output below.
    return cast(Callable[[Mapping[str, Any]], Mapping[str, Any]], fn)

# ──────────────────────────────────────────────────────────────────────────────
# Interactive
# ──────────────────────────────────────────────────────────────────────────────

def interactive_mode() -> None:
    print("\n=== StatLine (Adapter-Driven Interactive) ===\n")

    # Choose adapter
    names = list_names()
    if not names:
        print("No adapters found.")
        return
    print("Available adapters:", ", ".join(names))
    adapter_key = input(f"Adapter [{names[0]}]: ").strip().lower() or names[0]
    try:
        adp: Any = load_adapter(adapter_key)  # keep as Any; adapters are heterogeneous
    except Exception as e:
        print(f"Failed to load adapter '{adapter_key}': {e}")
        return

    # Optional team context
    try:
        team_wins = int(input("Team Wins [0]: ").strip() or "0")
        team_losses = int(input("Team Losses [0]: ").strip() or "0")
    except ValueError:
        team_wins, team_losses = 0, 0

    # Optional weights preset
    presets = list(getattr(adp, "weights", {}).keys())
    w_override: Optional[Dict[str, float]] = None
    if presets:
        default_preset = "pri" if "pri" in presets else presets[0]
        preset = input(f"Weights preset {presets} [{default_preset}]: ").strip().lower() or default_preset
        try:
            w_override = {str(k): float(v) for k, v in adp.weights[preset].items()}
        except Exception:
            print(f"Unknown preset '{preset}', using default '{default_preset}'.")
            w_override = {str(k): float(v) for k, v in adp.weights[default_preset].items()}

    # Collect rows repeatedly
    while True:
        print("\n--- Enter Raw Row Fields (hit Enter to keep 0) ---")

        # Metrics list from adapter; use YAML order
        metric_keys: List[str] = [m.key for m in getattr(adp, "metrics", [])]
        print(f"Adapter metrics: {', '.join(metric_keys)}")

        # Gather numeric inputs for metrics only
        raw_metrics: Dict[str, Any] = {}
        for key in metric_keys:
            raw_metrics[key] = _prompt_float_strict(key)

        # Free-text name (excluded from mapping)
        display_name = input("Display Name (optional): ").strip()

        # Map using adapter’s function
        try:
            mapper = _get_mapper(adp)
            mapped_any: Mapping[str, Any] = mapper(raw_metrics)
            mapped: Dict[str, Any] = dict(mapped_any)
        except Exception as e:
            print(f"Mapping error: {e}")
            continue

        # Score
        try:
            rows_in: List[Dict[str, Any]] = [mapped]
            results_list: List[Dict[str, Any]] = calculate_pri(
                rows_in,
                adapter=adp,
                team_wins=team_wins,
                team_losses=team_losses,
                weights_override=w_override,
                context=None,
            )
        except Exception as e:
            print(f"Scoring error: {e}")
            continue

        res = results_list[0]

        # Output
        print("\n" + "=" * 60)
        name = display_name or "(unnamed)"
        print(f"{name} — Adapter: {getattr(adp, 'key', adapter_key)}")
        print(f"PRI: {int(res['pri'])} / 99  (raw: {res['pri_raw']:.4f}, context: {res['context_used']})")

        print("\nBuckets:")
        for b, v in res["buckets"].items():
            print(f"  {b:<14} {v:.3f}")

        print("\nTop components:")
        comps = res["components"]
        top = sorted(comps.items(), key=lambda kv: kv[1], reverse=True)[: min(10, len(comps))]
        for k, v in top:
            print(f"  {k:<14} {v:.3f}")

        print("=" * 60)

        # Loop controls
        nxt = input("\n(N)ext | (C)hange adapter | (E)xit: ").strip().lower()
        if nxt == "c":
            return interactive_mode()
        if nxt == "e":
            print("\nExiting StatLine.")
            return


# Make runnable directly if desired
if __name__ == "__main__":
    try:
        interactive_mode()
    except (KeyboardInterrupt, EOFError):
        print("\nExiting StatLine.")
