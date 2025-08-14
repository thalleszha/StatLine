from __future__ import annotations

import csv
import sys
import importlib
from pathlib import Path
from typing import (
    Iterable, Optional, Dict, Any, List, Callable, Mapping, IO, cast
)

import typer

try:
    import yaml  # optional for YAML I/O
except Exception:
    yaml = None

from statline.core.calculator import interactive_mode
from statline.core.adapters import load as load_adapter, list_names
from statline.core.scoring import calculate_pri  # adapter-driven PRI

app = typer.Typer(no_args_is_help=True)

# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _name_for_row(raw: Mapping[str, Any]) -> str:
    return str(
        raw.get("display_name")
        or raw.get("name")
        or raw.get("player")
        or raw.get("id")
        or ""
    )

def _coerce_float(v: Any) -> float:
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        try:
            return float(v)
        except ValueError:
            return 0.0
    return 0.0

def _map_with_adapter(adp: Any, row: Mapping[str, Any]) -> Dict[str, float]:
    """
    Support adapters that implement either:
      - map_raw(row) -> Mapping
      - map_raw_to_metrics(row) -> Mapping
    Ensure str keys and float values for downstream scoring/CSV.
    """
    fn: Optional[Callable[[Mapping[str, Any]], Mapping[str, Any]]] = (
        getattr(adp, "map_raw", None) or getattr(adp, "map_raw_to_metrics", None)
    )
    if not callable(fn):
        raise typer.BadParameter(f"Adapter '{getattr(adp, 'KEY', adp)}' lacks map_raw/map_raw_to_metrics.")
    out = fn(row)  # type: ignore[misc]
    safe: Dict[str, float] = {}
    for k, v in dict(out).items():
        safe[str(k)] = _coerce_float(v)
    return safe

def _read_rows(input_path: Path) -> Iterable[Dict[str, Any]]:
    """
    Read input rows from YAML/CSV, or '-' for stdin CSV.
      - YAML: list[dict] or {rows: list[dict]}
      - CSV: header row required
    """
    if str(input_path) == "-":
        reader = csv.DictReader(sys.stdin)
        for row in reader:
            yield {str(k): v for k, v in row.items()}
        return

    if not input_path.exists():
        raise typer.BadParameter(f"Input file not found: {input_path}. Pass a YAML/CSV or use '-' for stdin.")

    suffix = input_path.suffix.lower()
    if suffix in {".yaml", ".yml"}:
        if yaml is None:
            raise typer.BadParameter("PyYAML not installed; cannot read YAML.")
        data = yaml.safe_load(input_path.read_text(encoding="utf-8"))
        src: Iterable[Mapping[str, Any]]
        if isinstance(data, dict) and isinstance(data.get("rows"), list):
            src = [r for r in data["rows"] if isinstance(r, dict)]
        elif isinstance(data, list):
            src = [r for r in data if isinstance(r, dict)]
        else:
            raise typer.BadParameter("YAML must be a list[dict] or {rows: list[dict]}.")
        for r in src:
            yield {str(k): v for k, v in r.items()}
        return

    if suffix == ".csv":
        with input_path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                yield {str(k): v for k, v in row.items()}
        return

    raise typer.BadParameter("Input must be .yaml/.yml or .csv (JSON not supported).")

def _write_csv(path: Path, rows: List[Dict[str, Any]], include_headers: bool = True) -> None:
    """
    Write rows to CSV with dynamic headers (union of keys across rows).
    Ensures headers are str. Places display_name/group_name first if present.
    Uses csv.writer to avoid DictWriter typing quirks.
    """
    if not rows:
        path.write_text("", encoding="utf-8")
        return

    fixed_front = [k for k in ("display_name", "group_name") if k in rows[0]]
    all_keys: set[str] = set()
    for r in rows:
        all_keys.update(str(k) for k in r.keys())
    for k in fixed_front:
        all_keys.discard(k)
    headers: List[str] = fixed_front + sorted(all_keys)

    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(cast(IO[str], f))
        if include_headers:
            w.writerow(headers)
        # build rows explicitly as List[List[str]]
        matrix: List[List[str]] = []
        for r in rows:
            matrix.append([str(r.get(k, "")) for k in headers])
        w.writerows(matrix)

def _load_bucket_weights(adapter_obj: Any, weights_path: Optional[Path], weights_preset: Optional[str]) -> Optional[Dict[str, float]]:
    """
    Return bucket weights (NOT per-metric) to pass to calculate_pri as an override.
    If neither a file nor a preset is available, return None.
    """
    if weights_path and weights_preset:
        raise typer.BadParameter("Specify either --weights or --weights-preset, not both.")

    if weights_path:
        if yaml is None:
            raise typer.BadParameter("PyYAML not installed; cannot read --weights YAML.")
        data = yaml.safe_load(weights_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise typer.BadParameter("--weights YAML must be a mapping of {bucket: weight}.")
        return {str(k): _coerce_float(v) for k, v in data.items()}

    presets = getattr(adapter_obj, "weights", None) or {}
    if not presets:
        return None

    preset_name = (weights_preset or "pri").lower()
    if preset_name not in presets:
        avail = ", ".join(sorted(presets.keys()))
        raise typer.BadParameter(f"Unknown weights preset '{preset_name}'. Available: {avail or '(none)'}")
    return {str(k): _coerce_float(v) for k, v in presets[preset_name].items()}

# Lazy loaders so Pylance doesn't error if modules are absent
def _lazy_cache_export(guild_id: str) -> List[Dict[str, Any]]:
    """
    Try to call statline.core.cache.get_mapped_rows_for_scoring(guild_id).
    Normalize to List[Dict[str, Any]] defensively so static typing stays happy.
    """
    try:
        mod = importlib.import_module("statline.core.cache")
        fn = getattr(mod, "get_mapped_rows_for_scoring", None)
        if not callable(fn):
            return []

        rows_obj: Any = fn(guild_id)  # dynamic/unknown type
        out: List[Dict[str, Any]] = []

        # Accept common iterables; ignore anything else
        if isinstance(rows_obj, list) or isinstance(rows_obj, tuple):
            for r in rows_obj:
                if isinstance(r, Mapping):
                    d = dict(cast(Mapping[str, Any], r))
                    out.append({str(k): v for k, v in d.items()})
            return out

        # Fallback: if it's a single mapping, wrap it; otherwise, ignore
        if isinstance(rows_obj, Mapping):
            d = dict(cast(Mapping[str, Any], rows_obj))
            return [{str(k): v for k, v in d.items()}]

        return []
    except Exception:
        return []


# ── replace _lazy_cache_context ───────────────────────────────────────────────
def _lazy_cache_context(guild_id: str) -> Optional[Dict[str, Dict[str, float]]]:
    """
    Try to call statline.core.cache.get_metric_context_ap(guild_id).
    Normalize to Dict[str, Dict[str, float]] defensively.
    """
    try:
        mod = importlib.import_module("statline.core.cache")
        fn = getattr(mod, "get_metric_context_ap", None)
        if not callable(fn):
            return None

        ctx_obj: Any = fn(guild_id)  # dynamic/unknown type
        if not isinstance(ctx_obj, Mapping):
            return None

        safe: Dict[str, Dict[str, float]] = {}
        for k, d in dict(cast(Mapping[str, Any], ctx_obj)).items():
            if isinstance(d, Mapping):
                dd: Dict[str, float] = {}
                for mk, mv in dict(cast(Mapping[str, Any], d)).items():
                    try:
                        dd[str(mk)] = float(mv) if mv is not None else 0.0
                    except Exception:
                        dd[str(mk)] = 0.0
                safe[str(k)] = dd
        return safe
    except Exception:
        return None


def _lazy_force_refresh(guild_id: str) -> None:
    try:
        mod = importlib.import_module("statline.core.refresh")
        fn = getattr(mod, "sync_guild_if_stale", None)
        if callable(fn):
            fn(guild_id, force=True)  # type: ignore[misc]
    except Exception:
        return

def _autobuild_stats_csv(output_path: Path, guild_id: str, refresh: bool) -> List[Dict[str, Any]]:
    if refresh:
        _lazy_force_refresh(guild_id)
    rows = _lazy_cache_export(guild_id)
    if not rows:
        raise typer.BadParameter(f"No cached rows for guild '{guild_id}'. Run a sync first or provide a CSV/YAML.")
    _write_csv(output_path, rows, include_headers=True)
    return rows

# ──────────────────────────────────────────────────────────────────────────────
# Typed shim around calculate_pri to satisfy Pylance
# ──────────────────────────────────────────────────────────────────────────────

def _calc_pri_typed(
    rows: List[Dict[str, Any]],
    adp: Any,
    *,
    team_wins: int,
    team_losses: int,
    weights_override: Optional[Dict[str, float]],
    context: Optional[Dict[str, Dict[str, float]]],
) -> List[Dict[str, Any]]:
    res = calculate_pri(
        rows,
        adapter=adp,
        team_wins=team_wins,
        team_losses=team_losses,
        weights_override=weights_override,
        context=context,
    )
    # ensure the type for the caller
    return cast(List[Dict[str, Any]], res)

# ──────────────────────────────────────────────────────────────────────────────
# Commands
# ──────────────────────────────────────────────────────────────────────────────

@app.command("interactive")
def interactive() -> None:
    """Run interactive adapter-driven calculator."""
    try:
        interactive_mode()
    except (KeyboardInterrupt, EOFError):
        print("\nExiting StatLine.")
        raise typer.Exit(code=0)

@app.command("adapters")
def adapters_list() -> None:
    """List available adapter keys."""
    for name in list_names():
        typer.echo(name)

@app.command("export-csv")
def export_csv(
    adapter: str = typer.Option(..., "--adapter", help="Adapter key (for validation only)"),
    guild_id: str = typer.Option(..., "--guild-id", help="Guild to export from"),
    out: Path = typer.Option(Path("stats.csv"), "--out", help="Destination CSV path"),
    include_headers: bool = typer.Option(True, "--headers/--no-headers", help="Include header row"),
    refresh: bool = typer.Option(False, "--refresh/--no-refresh", help="Force a Sheets refresh before export"),
) -> None:
    """Explicitly export the guild's mapped metrics to CSV (no scoring)."""
    _ = load_adapter(adapter)  # validate adapter exists
    rows = _autobuild_stats_csv(out, guild_id=guild_id, refresh=refresh)
    typer.secho(f"Wrote {out} ({len(rows)} rows).", fg=typer.colors.GREEN)

@app.command("score")
def score(
    adapter: str = typer.Option(..., "--adapter", help="Adapter key (e.g., rbw5, legacy, valorant)"),
    input_path: Path = typer.Argument(Path("stats.csv"), help="YAML/CSV understood by the adapter. If missing, use --guild-id to auto-build."),
    # Auto-build knobs
    guild_id: Optional[str] = typer.Option(None, "--guild-id", help="Guild to export from when auto-generating stats.csv"),
    refresh: bool = typer.Option(False, "--refresh/--no-refresh", help="Force a Sheets refresh before auto-generating"),
    # Weighting
    weights: Optional[Path] = typer.Option(None, "--weights", help="YAML mapping of {bucket: weight}"),
    weights_preset: Optional[str] = typer.Option("pri", "--weights-preset", help="Adapter preset name (default: 'pri')"),
    # Output
    out: Optional[Path] = typer.Option(None, "--out", help="Write results CSV (omit to print to stdout)"),
    include_headers: bool = typer.Option(True, "--headers/--no-headers", help="Include header row in CSV output"),
    # Contextual team multiplier
    team_wins: int = typer.Option(0, "--team-wins", help="Team wins for small PRI multiplier"),
    team_losses: int = typer.Option(0, "--team-losses", help="Team losses for small PRI multiplier"),
) -> None:
    """
    Batch score via an adapter (YAML/CSV input; CSV/STDOUT output).
    If the input file is missing and --guild-id is provided, the CLI will
    auto-create 'stats.csv' from the DB cache (entities/metrics) and then score it.
    """
    adp = load_adapter(adapter)
    bucket_weights = _load_bucket_weights(adp, weights, weights_preset)

    mapped_rows: Optional[List[Dict[str, Any]]] = None

    # Auto-build stats.csv from DB if missing and guild_id provided
    if not input_path.exists() and str(input_path) != "-":
        if guild_id is None:
            raise typer.BadParameter(
                f"{input_path} does not exist. Provide --guild-id to auto-generate, "
                "or pass a YAML/CSV file, or use '-' for stdin."
            )
        mapped_rows = _autobuild_stats_csv(input_path, guild_id=guild_id, refresh=refresh)
        typer.secho(f"Auto-generated {input_path} from guild '{guild_id}'.", fg=typer.colors.GREEN)

    # If we just generated the CSV, we already have canonical rows; otherwise read file and map
    if mapped_rows is None:
        raw_rows = list(_read_rows(input_path))
        mapped_rows = []
        for r in raw_rows:
            m = _map_with_adapter(adp, r)
            sanity = getattr(adp, "sanity", None)
            if callable(sanity):
                sanity(m)
            mapped_rows.append(m)

    # Determine context: DB (preferred) if a guild is given and function exists, else batch-derived
    context = _lazy_cache_context(guild_id) if guild_id else None

    # Narrow Optional for Pylance and copy into concrete local
    assert mapped_rows is not None
    mapped_rows_list: List[Dict[str, Any]] = mapped_rows

    # PRI scoring via typed shim
    results_list: List[Dict[str, Any]] = _calc_pri_typed(
        mapped_rows_list,
        adp,
        team_wins=team_wins,
        team_losses=team_losses,
        weights_override=bucket_weights,
        context=context,
    )

    # Output: name, pri (0–99), pri_raw (0..1), context_used
    out_fields: List[str] = ["name", "pri", "pri_raw", "context_used"]
    rows_out: List[Dict[str, Any]] = []
    for i in range(len(mapped_rows_list)):
        raw = mapped_rows_list[i]
        res = results_list[i]
        rows_out.append({
            "name": _name_for_row(raw) or raw.get("display_name") or "(unnamed)",
            "pri": int(res.get("pri", 0)),
            "pri_raw": f"{float(res.get('pri_raw', 0.0)):.4f}",
            "context_used": res.get("context_used", ""),
        })

    # Write CSV using csv.writer with string matrix
    if out:
        with out.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(cast(IO[str], f))
            if include_headers:
                w.writerow(out_fields)
            matrix: List[List[str]] = [[str(row.get(k, "")) for k in out_fields] for row in rows_out]
            w.writerows(matrix)
    else:
        w = csv.writer(cast(IO[str], sys.stdout))
        if include_headers:
            w.writerow(out_fields)
        matrix: List[List[str]] = [[str(row.get(k, "")) for k in out_fields] for row in rows_out]
        w.writerows(matrix)

def main() -> None:
    try:
        app()
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        raise typer.Exit(code=1)

if __name__ == "__main__":
    main()
