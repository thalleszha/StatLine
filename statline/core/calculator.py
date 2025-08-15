from __future__ import annotations

from typing import Dict, Any, List, Optional, Mapping, Callable, Iterable, cast, Tuple

from .adapters import list_names, load as load_adapter
from .scoring import calculate_pri
import typer

try:
    from rich.console import Console
    from rich.table import Table
    _RICH_OK = True
    _console = Console()
except Exception:
    _RICH_OK = False
    _console = None  # type: ignore[assignment]


# ──────────────────────────────────────────────────────────────────────────────
# Input helpers
# ──────────────────────────────────────────────────────────────────────────────

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

def _sanitize_numeric_metrics(raw_metrics: Mapping[str, Any]) -> Dict[str, Any]:
    """
    Strip and coerce numeric-like metric values; leave obviously non-numeric fields as-is.
    """
    numeric_metrics: Dict[str, Any] = {}
    for k, v in raw_metrics.items():
        if isinstance(v, str):
            vv = v.strip()
            if vv == "":
                numeric_metrics[k] = 0.0
                continue
            try:
                numeric_metrics[k] = float(vv.replace(",", "."))
                continue
            except ValueError:
                # keep non-numeric string as-is (e.g., free-text labels)
                pass
        numeric_metrics[k] = v
    return numeric_metrics

def _get_mapper(adapter: Any) -> Callable[[Mapping[str, Any]], Mapping[str, Any]]:
    """
    Return the adapter's mapping function with a tolerant signature.
    Prefer map_raw, else map_raw_to_metrics.
    """
    fn: Any = getattr(adapter, "map_raw", None)
    if not callable(fn):
        fn = getattr(adapter, "map_raw_to_metrics", None)
    if not callable(fn):
        raise RuntimeError("Adapter has neither map_raw nor map_raw_to_metrics.")
    return cast(Callable[[Mapping[str, Any]], Mapping[str, Any]], fn)

def safe_map_raw(adapter: Any, raw_metrics: Dict[str, Any]) -> Dict[str, Any]:
    """
    Wrap the adapter's map function with input sanitation and SyntaxError debugging.
    Ensures numeric metrics are coerced before any eval-like paths.
    """
    mapper = _get_mapper(adapter)
    numeric_metrics = _sanitize_numeric_metrics(raw_metrics)
    try:
        mapped_any = mapper(numeric_metrics)
        return dict(mapped_any)
    except SyntaxError as se:
        print("\n=== Mapping Syntax Error ===")
        print(f"Error: {se}")
        print("Raw metrics (sanitized):", numeric_metrics)
        eval_expr = getattr(adapter, "eval_expr", None)
        if eval_expr:
            print("Eval expression:", eval_expr)
        print("============================\n")
        raise

# ──────────────────────────────────────────────────────────────────────────────
# Interactive
# ──────────────────────────────────────────────────────────────────────────────

def interactive_mode(*, show_banner: bool = True) -> None:
    """
    Adapter-driven interactive scoring with Typer-style prompts and output.
    Set show_banner=False when called from the Typer CLI to avoid double headers.
    """
    def banner() -> None:
        typer.secho("=== StatLine — Adapter-Driven Scoring ===", fg=typer.colors.CYAN, bold=True)

    def prompt_int(label: str, default: int = 0, min_value: int | None = 0) -> int:
        while True:
            s = typer.prompt(label, default=str(default))
            try:
                val = int(str(s).strip() or default)
                if min_value is not None and val < min_value:
                    raise ValueError
                return val
            except Exception:
                typer.secho(f"  Enter an integer >= {min_value if min_value is not None else '-∞'}.",
                            fg=typer.colors.RED)

    def prompt_float(label: str, default: float = 0.0) -> float:
        while True:
            s = typer.prompt(label, default=str(default))
            s = str(s).strip().replace(",", ".")
            if s == "":
                return default
            try:
                return float(s)
            except ValueError:
                typer.secho("  Enter a number (e.g., 0.7).", fg=typer.colors.RED)

    def menu_select(title: str, options: List[str], default_index: int = 0) -> str:
        """
        Minimal Typer-style numeric selector. Returns the chosen string.
        """
        if not options:
            raise typer.BadParameter(f"No options for {title}")
        typer.secho(title, fg=typer.colors.MAGENTA, bold=True)
        for i, opt in enumerate(options, 1):
            typer.echo(f"  {i}. {opt}")
        while True:
            raw = typer.prompt("Select", default=str(default_index + 1)).strip()
            if raw.isdigit():
                idx = int(raw) - 1
                if 0 <= idx < len(options):
                    return options[idx]
            # also allow direct text entry (exact match)
            if raw in options:
                return raw
            typer.secho("  Invalid selection. Choose a number from the list or an exact option.",
                        fg=typer.colors.RED)

    def get_mapper(adp: Any) -> Callable[[Mapping[str, Any]], Mapping[str, Any]]:
        fn = getattr(adp, "map_raw", None) or getattr(adp, "map_raw_to_metrics", None)
        if not callable(fn):
            raise RuntimeError("Adapter lacks map_raw/map_raw_to_metrics.")
        return fn  # type: ignore[return-value]

    def sanitize_numeric(raw: Mapping[str, Any]) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        for k, v in raw.items():
            if isinstance(v, str):
                s = v.strip().replace(",", ".")
                if s == "":
                    out[k] = 0.0
                    continue
                try:
                    out[k] = float(s)
                    continue
                except ValueError:
                    # keep non-numeric text (e.g., labels)
                    pass
            out[k] = v
        return out

    def choose_adapter(default_key: Optional[str]) -> Tuple[str, Any]:
        names = list_names()
        if not names:
            typer.secho("No adapters found.", fg=typer.colors.RED)
            raise typer.Exit(1)
        default_idx = max(0, names.index(default_key)) if default_key in names else 0
        choice = menu_select("Available adapters:", names, default_idx)
        try:
            adp = load_adapter(choice)
        except Exception as e:
            typer.secho(f"Failed to load adapter '{choice}': {e}", fg=typer.colors.RED)
            return choose_adapter(default_key)
        return choice, adp

    def choose_weights(adp: Any) -> Optional[Dict[str, float]]:
        presets = getattr(adp, "weights", {}) or {}
        if not isinstance(presets, dict) or not presets:
            return None
        names = list(presets.keys())
        default_idx = names.index("pri") if "pri" in names else 0
        chosen = menu_select("Weight presets:", names, default_idx)
        try:
            w = {str(k): float(v) for k, v in presets[chosen].items()}
        except Exception:
            typer.secho("  Bad preset weights; ignoring override.", fg=typer.colors.RED)
            return None
        total = sum(w.values())
        if not (0.999 <= total <= 1.001):
            typer.secho(f"  Preset weights must sum to 1.0 (got {total:.6f}); ignoring override.",
                        fg=typer.colors.YELLOW)
            return None
        return w

    def render_result(name: str, adapter_key: str, res: Dict[str, Any]) -> None:
        pri = int(res.get("pri", 0))
        pri_raw = float(res.get("pri_raw", 0.0))
        ctx_used = res.get("context_used", "")
        header = f"{name} — Adapter: {adapter_key}"
        typer.secho("\n" + header, bold=True)
        typer.echo(f"PRI: {pri} / 99  (raw: {pri_raw:.4f}, context: {ctx_used})")

        buckets = res.get("buckets", {}) or {}
        comps = res.get("components", {}) or {}

        if _RICH_OK and _console:
            if buckets:
                t = Table(title="Buckets", show_lines=False)
                t.add_column("Bucket", style="bold")
                t.add_column("Value")
                for b, v in buckets.items():
                    try:
                        t.add_row(str(b), f"{float(v):.3f}")
                    except Exception:
                        t.add_row(str(b), str(v))
                _console.print(t)
            if comps:
                t = Table(title="Top components", show_lines=False)
                t.add_column("Component", style="bold")
                t.add_column("Value")
                for k, v in sorted(comps.items(), key=lambda kv: kv[1], reverse=True)[:10]:
                    try:
                        t.add_row(str(k), f"{float(v):.3f}")
                    except Exception:
                        t.add_row(str(k), str(v))
                _console.print(t)
        else:
            # Plain fallback
            if buckets:
                typer.secho("\nBuckets:", bold=True)
                for b, v in buckets.items():
                    try:
                        typer.echo(f"  {b:<14} {float(v):.3f}")
                    except Exception:
                        typer.echo(f"  {b:<14} {v}")
            if comps:
                typer.secho("\nTop components:", bold=True)
                for k, v in sorted(comps.items(), key=lambda kv: kv[1], reverse=True)[:10]:
                    try:
                        typer.echo(f"  {k:<14} {float(v):.3f}")
                    except Exception:
                        typer.echo(f"  {k:<14} {v}")

    # ── flow ──────────────────────────────────────────────────────────────────
    if show_banner:
        banner()

    adapter_default: Optional[str] = None
    while True:
        adapter_key, adp = choose_adapter(adapter_default)
        adapter_default = getattr(adp, "KEY", None) or getattr(adp, "key", None) or adapter_key

        wins = prompt_int("Team Wins", default=0, min_value=0)
        losses = prompt_int("Team Losses", default=0, min_value=0)
        weights_override = choose_weights(adp)

        while True:
            typer.secho("\n--- Enter Raw Row Fields (press Enter for 0) ---", fg=typer.colors.BLUE, bold=True)
            metric_keys: List[str] = [getattr(m, "key", str(m)) for m in getattr(adp, "metrics", [])]
            if metric_keys:
                typer.echo("Metrics: " + ", ".join(metric_keys))

            raw_metrics: Dict[str, Any] = {}
            for key in metric_keys:
                raw_metrics[key] = prompt_float(key, default=0.0)

            display_name = typer.prompt("Display Name (optional)", default="").strip()

            try:
                mapper = get_mapper(adp)
                mapped_any = mapper(sanitize_numeric(raw_metrics))
                mapped = dict(mapped_any)
            except Exception as e:
                typer.secho(f"Mapping error: {e}", fg=typer.colors.RED)
                continue

            try:
                results = calculate_pri(
                    [mapped],
                    adapter=adp,
                    team_wins=wins,
                    team_losses=losses,
                    weights_override=weights_override,
                    context=None,
                )
            except Exception as e:
                typer.secho(f"Scoring error: {e}", fg=typer.colors.RED)
                continue

            name = display_name or "(unnamed)"
            render_result(name, adapter_default or adapter_key, results[0])

            # Navigation
            choice = menu_select("Next step:", ["Next row", "Change adapter", "Exit"], default_index=0)
            if choice == "Change adapter":
                break
            if choice == "Exit":
                typer.echo("\nExiting StatLine.")
                return
            # else: loop for next row with same adapter


# Make runnable directly if desired
if __name__ == "__main__":
    try:
        interactive_mode()
    except (KeyboardInterrupt, EOFError):
        print("\nExiting StatLine.")
