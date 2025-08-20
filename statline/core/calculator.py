# statline/core/calculator.py
from __future__ import annotations

# ── stdlib ────────────────────────────────────────────────────────────────────
import os
import sys
from contextlib import nullcontext
from typing import Any, Callable, Dict, List, Mapping, Optional, Protocol, Sequence, Tuple, cast

# ── third-party ───────────────────────────────────────────────────────────────
import typer

# ── first-party ───────────────────────────────────────────────────────────────
from statline.utils.timing import StageTimes

from .adapters import list_names
from .adapters import load as load_adapter
from .scoring import calculate_pri

# ── typing helpers ────────────────────────────────────────────────────────────
Row = Dict[str, Any]
Rows = List[Row]
_console: Optional[Any]
_rich_ok: bool
try:
    from rich.console import Console
    _console = Console()
    _rich_ok = True
except Exception:
    _console = None
    _rich_ok = False

class AdapterProto(Protocol):
    """Minimal surface used by the calculator."""
    KEY: str

    # Some adapters expose `metrics` (iterable of objects with a `key` attr)
    metrics: Sequence[Any] | Any

    # Adapters may provide either of these mapping functions.
    def map_raw_to_metrics(self, raw: Mapping[str, Any]) -> Mapping[str, Any]: ...
    def map_raw(self, raw: Mapping[str, Any]) -> Mapping[str, Any]: ...

    # Optional helper some adapters provide:
    def sanity(self, metrics: Mapping[str, Any]) -> None: ...  # pragma: no cover


# ──────────────────────────────────────────────────────────────────────────────
# Input helpers
# ──────────────────────────────────────────────────────────────────────────────

def _sanitize_numeric_metrics(raw_metrics: Mapping[str, Any]) -> Dict[str, Any]:
    """Coerce string numbers (including '1,23') to float; blank → 0.0."""
    numeric_metrics: Dict[str, Any] = {}
    for k, v in raw_metrics.items():
        if isinstance(v, str):
            s = v.strip()
            if s == "":
                numeric_metrics[k] = 0.0
                continue
            try:
                numeric_metrics[k] = float(s.replace(",", "."))
                continue
            except ValueError:
                pass
        numeric_metrics[k] = v
    return numeric_metrics


def _get_mapper(adapter: AdapterProto) -> Callable[[Mapping[str, Any]], Mapping[str, Any]]:
    """Return adapter's mapping function (prefers map_raw_to_metrics)."""
    fn: Optional[Callable[[Mapping[str, Any]], Mapping[str, Any]]] = None
    if hasattr(adapter, "map_raw_to_metrics") and callable(getattr(adapter, "map_raw_to_metrics")):
        fn = cast(Callable[[Mapping[str, Any]], Mapping[str, Any]], getattr(adapter, "map_raw_to_metrics"))
    elif hasattr(adapter, "map_raw") and callable(getattr(adapter, "map_raw")):
        fn = cast(Callable[[Mapping[str, Any]], Mapping[str, Any]], getattr(adapter, "map_raw"))
    if fn is None:
        raise RuntimeError("Adapter has neither map_raw nor map_raw_to_metrics.")
    return fn


def safe_map_raw(adapter: AdapterProto, raw_metrics: Dict[str, Any]) -> Dict[str, Any]:
    """Map a row through the adapter, with numeric sanitization and good errors."""
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


def _print_timing(T: StageTimes) -> None:
    if not T.items:
        return
    total = sum(ms for _, ms in T.items)
    parts = ", ".join(f"{name} {ms:.2f}" for name, ms in T.items)
    print(f"\n⏱ {total:.2f} ms total ({parts})", file=sys.stderr)

    # Pretty table if Rich is available and we're on a TTY.
    if _rich_ok and _console and sys.stderr.isatty():
        try:
            from rich.table import Table
        except Exception:
            return
        tbl = Table(title="Timing (ms)", show_lines=False)
        tbl.add_column("Stage", style="bold")
        tbl.add_column("ms", justify="right")
        for name, ms in T.items:
            tbl.add_row(name, f"{ms:.2f}")
        tbl.add_row("—", "—")
        tbl.add_row("TOTAL", f"{total:.2f}")
        _console.print(tbl)


# ──────────────────────────────────────────────────────────────────────────────
# Interactive
# ──────────────────────────────────────────────────────────────────────────────

def interactive_mode(*, show_banner: bool = True, show_timing: Optional[bool] = None) -> None:
    """
    Adapter-driven interactive scoring with prompts and formatted output.
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
                typer.secho(
                    f"  Enter an integer >= {min_value if min_value is not None else '-∞'}.",
                    fg=typer.colors.RED,
                )

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
        if not options:
            raise typer.BadParameter(f"No options for {title}")
        typer.secho(title, fg=typer.colors.MAGENTA, bold=True)
        for i, opt in enumerate(options, 1):
            typer.echo(f"  {i}. {opt}")
        while True:
            raw_any = typer.prompt("Select", default=str(default_index + 1))
            raw = str(raw_any).strip()
            if raw.isdigit():
                idx = int(raw) - 1
                if 0 <= idx < len(options):
                    return options[idx]
            if raw in options:
                return raw
            typer.secho(
                "  Invalid selection. Choose a number from the list or an exact option.",
                fg=typer.colors.RED,
            )

    def get_mapper(adp: AdapterProto) -> Callable[[Mapping[str, Any]], Mapping[str, Any]]:
        return _get_mapper(adp)

    def sanitize_numeric(raw: Mapping[str, Any]) -> Dict[str, Any]:
        return _sanitize_numeric_metrics(raw)

    def choose_adapter(default_key: Optional[str]) -> Tuple[str, AdapterProto]:
        names = list_names()
        if not names:
            typer.secho("No adapters found.", fg=typer.colors.RED)
            raise typer.Exit(1)
        default_idx = max(0, names.index(default_key)) if (default_key and default_key in names) else 0
        choice = menu_select("Available adapters:", names, default_idx)
        try:
            adp = cast(AdapterProto, load_adapter(choice))
        except Exception as e:
            typer.secho(f"Failed to load adapter '{choice}': {e}", fg=typer.colors.RED)
            return choose_adapter(default_key)
        return choice, adp

    def choose_weights(adp: AdapterProto) -> Optional[Dict[str, float]]:
        # Adapter-provided presets are a mapping: preset_name -> mapping of bucket -> weight
        raw_presets = getattr(adp, "weights", {}) or {}
        presets: Dict[str, Mapping[str, Any]] = cast(Dict[str, Mapping[str, Any]], raw_presets)
        if not presets:
            return None

        names: List[str] = list(presets.keys())  # keys are now str, not Unknown
        default_idx = names.index("pri") if "pri" in names else 0
        chosen = menu_select("Weight presets:", names, default_idx)

        try:
            selected: Mapping[str, Any] = presets[chosen]   # concrete Mapping[str, Any]
            # Iterate with precise types so k and v aren’t Unknown
            w: Dict[str, float] = {str(k): float(v) for k, v in selected.items()}
        except Exception:
            typer.secho("  Bad preset weights; ignoring override.", fg=typer.colors.RED)
            return None

        total = sum(w.values())
        if not (0.999 <= total <= 1.001):
            typer.secho(
                f"  Preset weights must sum to 1.0 (got {total:.6f}); ignoring override.",
                fg=typer.colors.YELLOW,
            )
            return None
        return w

    def render_result(name: str, adapter_key: str, res: Mapping[str, Any]) -> None:
        pri = int(res.get("pri", 0))
        pri_raw = float(res.get("pri_raw", 0.0))
        ctx_used = res.get("context_used", "")
        header = f"{name} — Adapter: {adapter_key}"
        typer.secho("\n" + header, bold=True)
        typer.echo(f"PRI: {pri} / 99  (raw: {pri_raw:.4f}, context: {ctx_used})")

        buckets = cast(Mapping[str, Any], res.get("buckets", {}) or {})
        comps = cast(Mapping[str, Any], res.get("components", {}) or {})

        if _rich_ok and _console:
            # Import class into a local variable instead of reassigning the symbol "Table"
            table_cls: Optional[Any] = None
            try:
                from rich.table import Table as _RichTable
                table_cls = _RichTable
            except Exception:
                table_cls = None

            if table_cls is not None:
                if buckets:
                    t = table_cls(title="Buckets", show_lines=False)
                    t.add_column("Bucket", style="bold")
                    t.add_column("Value")
                    for b, v in buckets.items():
                        try:
                            t.add_row(str(b), f"{float(v):.3f}")
                        except Exception:
                            t.add_row(str(b), str(v))
                    _console.print(t)
                if comps:
                    t = table_cls(title="Top components", show_lines=False)
                    t.add_column("Component", style="bold")
                    t.add_column("Value")
                    for k, v in sorted(comps.items(), key=lambda kv: kv[1], reverse=True)[:10]:
                        try:
                            t.add_row(str(k), f"{float(v):.3f}")
                        except Exception:
                            t.add_row(str(k), str(v))
                    _console.print(t)
                return

        # Plain-text fallback
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
            typer.secho(
                "\n--- Enter Raw Row Fields (press Enter for 0) ---",
                fg=typer.colors.BLUE,
                bold=True,
            )
            # metrics may be a list of objects with `key`, or raw strings; normalize to strings
            metrics_any = getattr(adp, "metrics", []) or []
            metric_keys: List[str] = [getattr(m, "key", str(m)) for m in metrics_any]
            if metric_keys:
                typer.echo("Metrics: " + ", ".join(metric_keys))

            raw_metrics: Dict[str, Any] = {}
            for key in metric_keys:
                raw_metrics[key] = prompt_float(key, default=0.0)

            display_name = typer.prompt("Display Name (optional)", default="").strip()

            timing_enabled = (show_timing is True) or (
                show_timing is None and (os.getenv("STATLINE_DEBUG") == "1" or os.getenv("STATLINE_TIMING") == "1")
            )
            T = StageTimes() if timing_enabled else None

            try:
                with (T.stage("sanitize_map") if T else nullcontext()):
                    mapper = get_mapper(adp)
                    mapped_any = mapper(sanitize_numeric(raw_metrics))
                    mapped = dict(mapped_any)

                with (T.stage("score") if T else nullcontext()):
                    results = calculate_pri(
                        [mapped],
                        adapter=adp,
                        team_wins=wins,
                        team_losses=losses,
                        weights_override=weights_override,
                        context=None,
                        _timing=T,  # inner-stage breakdown
                    )

                with (T.stage("render") if T else nullcontext()):
                    name = display_name or "(unnamed)"
                    render_result(name, adapter_default or adapter_key, results[0])

            except Exception as e:
                typer.secho(f"Error: {e}", fg=typer.colors.RED)
                continue
            finally:
                if T is not None:
                    _print_timing(T)

            choice = menu_select("Next step:", ["Next row", "Change adapter", "Exit"], default_index=0)
            if choice == "Change adapter":
                break
            if choice == "Exit":
                typer.echo("\nExiting StatLine.")
                return


if __name__ == "__main__":
    try:
        interactive_mode()
    except (KeyboardInterrupt, EOFError):
        print("\nExiting StatLine.")
