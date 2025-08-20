# scripts/dev_seed.py
from __future__ import annotations

import csv
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Tuple

import typer
from statline.core.adapters import load as load_adapter
from statline.core.db import get_conn
from statline.core.guild_manager import ensure_guild_entry, now_ts

app = typer.Typer(no_args_is_help=True)

TEST_GUILD_ID = "dev-guild"

# ──────────────────────────────────────────────────────────────────────────────
# IO helpers (YAML/CSV) — same conventions as CLI
# ──────────────────────────────────────────────────────────────────────────────

try:
    import yaml
except Exception:
    yaml = None

def _iter_rows(input_path: Path) -> Iterable[Dict[str, Any]]:
    sfx = input_path.suffix.lower()
    if sfx in {".yaml", ".yml"}:
        if yaml is None:
            raise typer.BadParameter("PyYAML not installed; cannot read YAML.")
        data = yaml.safe_load(input_path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and "rows" in data and isinstance(data["rows"], list):
            for r in data["rows"]:   # pyright: ignore[reportUnknownVariableType]
                if isinstance(r, dict):
                    yield r
            return
        if isinstance(data, list):
            for r in data:   # pyright: ignore[reportUnknownVariableType]
                if isinstance(r, dict):
                    yield r
            return
        raise typer.BadParameter("YAML must be list[dict] or {rows: list[dict]}.")
    elif sfx == ".csv":
        with input_path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                yield dict(row)
        return
    else:
        raise typer.BadParameter("Input must be .yaml/.yml or .csv")

# ──────────────────────────────────────────────────────────────────────────────
# Schema (adapter-agnostic)
# ──────────────────────────────────────────────────────────────────────────────

def _ensure_seed_schema() -> None:
    """
    Generic, title-agnostic storage:
      - entities: who/what we're scoring (per guild), with an optional group
      - metrics:  per-entity per-metric numeric values from the adapter
    """
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS entities (
                guild_id     TEXT NOT NULL,
                fuzzy_key    TEXT NOT NULL,       -- lowercase display name or stable id
                display_name TEXT NOT NULL,
                group_name   TEXT,                -- optional (team/agent/role/etc.)
                PRIMARY KEY (guild_id, fuzzy_key)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS metrics (
                guild_id    TEXT NOT NULL,
                fuzzy_key   TEXT NOT NULL,
                metric_key  TEXT NOT NULL,
                metric_value REAL NOT NULL DEFAULT 0,
                PRIMARY KEY (guild_id, fuzzy_key, metric_key),
                FOREIGN KEY (guild_id, fuzzy_key)
                    REFERENCES entities (guild_id, fuzzy_key)
                    ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_metrics_lookup
            ON metrics (guild_id, metric_key)
            """
        )

# ──────────────────────────────────────────────────────────────────────────────
# Upserts
# ──────────────────────────────────────────────────────────────────────────────

def _upsert_entity(guild_id: str, display_name: str, group_name: Optional[str]) -> str:
    fuzzy = display_name.strip().lower()
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO entities (guild_id, fuzzy_key, display_name, group_name)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(guild_id, fuzzy_key) DO UPDATE SET
                display_name = excluded.display_name,
                group_name   = excluded.group_name
            """,
            (guild_id, fuzzy, display_name, group_name),
        )
    return fuzzy

def _upsert_metrics(guild_id: str, fuzzy: str, mapped: Dict[str, Any]) -> None:
    rows: list[Tuple[str, str, str, float]] = []
    for k, v in mapped.items():
        try:
            val = float(v)
        except (TypeError, ValueError):
            # silently skip non-numeric values
            continue
        rows.append((guild_id, fuzzy, k, val))
    if not rows:
        return
    with get_conn() as conn:
        conn.executemany(
            """
            INSERT INTO metrics (guild_id, fuzzy_key, metric_key, metric_value)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(guild_id, fuzzy_key, metric_key) DO UPDATE SET
                metric_value = excluded.metric_value
            """,
            rows,
        )

# ──────────────────────────────────────────────────────────────────────────────
# Main seed command
# ──────────────────────────────────────────────────────────────────────────────

@app.command()
def seed(
    input_path: Path = typer.Argument(..., help="YAML/CSV of raw rows for the chosen adapter"),
    adapter: str = typer.Option(..., "--adapter", "-a", help="Adapter key (e.g., legacy, rbw5, valorant)"),
    guild_id: str = typer.Option(TEST_GUILD_ID, "--guild-id", help="Target guild id"),
    group_key: Optional[str] = typer.Option(None, "--group-key", help="Optional raw field to store as group (e.g., 'team', 'agent')"),
    name_keys: str = typer.Option("display_name,name,player,id", "--name-keys", help="Comma-separated raw fields to use for display name (first hit wins)"),
) -> None:
    """
    Seed the dev DB using a REAL adapter:
      - Reads raw rows
      - Maps with adapter.map_raw
      - Writes entities + per-metric values adapter-agnostically
      - Touches guild_config.last_sync_ts
    """
    # Ensure the guild exists so other flows work
    ensure_guild_entry(guild_id, sheet_key="dev-seed", sheet_tab="STATS")

    # Ensure generic schema
    _ensure_seed_schema()

    # Load adapter
    adp = load_adapter(adapter)

    # Read raw rows
    rows = list(_iter_rows(input_path))
    if not rows:
        raise typer.BadParameter("No rows to seed.")

    name_fields = [s.strip() for s in name_keys.split(",") if s.strip()]

    total = 0
    for raw in rows:
        # Select display name from candidate fields
        display = ""
        for k in name_fields:
            if k in raw and str(raw[k]).strip():
                display = str(raw[k]).strip()
                break
        if not display:
            # Last-ditch: stringify the whole row id-like
            display = str(raw.get("display_name") or raw.get("name") or raw.get("player") or raw.get("id") or f"entity-{total+1}")

        group_val = None
        if group_key:
            gv = raw.get(group_key)
            if gv is not None and str(gv).strip():
                group_val = str(gv).strip()

        # Map raw → canonical metrics via the real adapter
        mapped = adp.map_raw(raw)

        fuzzy = _upsert_entity(guild_id, display, group_val)
        _upsert_metrics(guild_id, fuzzy, mapped)
        total += 1

    # Touch last_sync_ts so caches consider fresh
    ts = now_ts()
    with get_conn() as conn:
        conn.execute(
            "UPDATE guild_config SET last_sync_ts = ?, updated_ts = ? WHERE guild_id = ?",
            (ts, ts, guild_id),
        )

    typer.echo(f"Seeded {total} row(s) into guild '{guild_id}' using adapter '{adp.key}'. ✅")

if __name__ == "__main__":
    try:
        app()
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        raise typer.Exit(code=1)
