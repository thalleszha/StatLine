from __future__ import annotations
import os, sqlite3
from pathlib import Path

_DB_DEFAULT = Path(__file__).resolve().parents[2] / "data" / "statline.db"

def get_db_path() -> str:
    return os.getenv("STATLINE_DB", str(_DB_DEFAULT))

def get_conn() -> sqlite3.Connection:
    # isolation_level=None -> autocommit
    conn = sqlite3.connect(get_db_path(), isolation_level=None)
    conn.row_factory = sqlite3.Row
    return conn

__all__ = ["get_conn", "get_db_path"]