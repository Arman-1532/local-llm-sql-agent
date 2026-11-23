#!/usr/bin/env python3
"""CLI script to build or rebuild the deterministic SQLite database."""

import os
import sys

# Ensure src/ is on PYTHONPATH
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from local_sql_agent.database.builder import build_database
from local_sql_agent.database.connection import DEFAULT_DB_PATH


def main():
    db_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_DB_PATH
    print(f"Building SQLite database at: {db_path} ...")
    path = build_database(db_path=db_path)
    print(f"✓ Database successfully built and populated at: {path}")


if __name__ == "__main__":
    main()
