"""Database connection module.
Provides URI read-only connection enforcement and database path resolution.
"""

import os
import sqlite3
from typing import Optional

# Path to data/store.db relative to project root
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../"))
DEFAULT_DB_PATH = os.path.join(_PROJECT_ROOT, "data", "store.db")


def get_default_db_path() -> str:
    """Returns the default database file path."""
    return DEFAULT_DB_PATH


def get_read_only_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    """Opens and returns an SQLite database connection in strict READ-ONLY mode.
    
    Uses SQLite URI `file:<path>?mode=ro`.
    Raises FileNotFoundError if the database file does not exist.
    """
    target = os.path.abspath(db_path or DEFAULT_DB_PATH)
    if not os.path.exists(target):
        raise FileNotFoundError(f"Database file not found at: {target}")

    uri = f"file:{target}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=10.0)
    conn.row_factory = sqlite3.Row
    return conn


def get_write_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    """Opens a standard read-write connection used exclusively by the builder."""
    target = os.path.abspath(db_path or DEFAULT_DB_PATH)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    conn = sqlite3.connect(target, timeout=10.0)
    conn.row_factory = sqlite3.Row
    return conn
