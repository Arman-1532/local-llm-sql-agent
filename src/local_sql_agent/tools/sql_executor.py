"""SQL Executor Tool.
Enforces read-only safety:
- Accepts ONLY SELECT and WITH statements.
- Rejects DDL and DML keywords (DROP, DELETE, UPDATE, INSERT, ALTER, CREATE, ATTACH, PRAGMA, etc.).
- Rejects multi-statement injection (semicolons).
- Enforces strict row limits.
- Opens SQLite database in URI read-only mode (file:<path>?mode=ro).
"""

import os
import re
import sqlite3
from typing import Any, Dict, List, Optional

from local_sql_agent.database.connection import DEFAULT_DB_PATH, get_read_only_connection


class ReadOnlySecurityError(Exception):
    """Raised when an unauthorized, non-read-only, or multi-statement SQL query is attempted."""
    pass


FORBIDDEN_KEYWORDS = {
    "drop", "delete", "update", "insert", "alter", "create", "attach", "detach",
    "pragma", "replace", "truncate", "vacuum", "grant", "revoke", "exec", "execute",
    "into", "commit", "rollback", "savepoint", "reindex"
}


def validate_read_only_sql(query: str) -> None:
    """Validates that a SQL query is strictly a single, read-only SELECT statement.
    
    Raises:
        ReadOnlySecurityError: If query is empty, contains multiple statements, or contains non-SELECT operations.
    """
    if not query or not query.strip():
        raise ReadOnlySecurityError("Security Error: Empty SQL query.")

    # Strip single line comments (-- ...)
    clean = re.sub(r"--[^\n]*", " ", query)
    # Strip block comments (/* ... */)
    clean = re.sub(r"/\*.*?\*/", " ", clean, flags=re.DOTALL).strip()

    if not clean:
        raise ReadOnlySecurityError("Security Error: Query contains only comments.")

    # Check for multi-statements separated by semicolons
    semicolon_parts = [p.strip() for p in clean.split(";") if p.strip()]
    if len(semicolon_parts) > 1:
        raise ReadOnlySecurityError("Security Error: Multiple statements detected. Only a single SELECT statement is permitted.")

    statement = semicolon_parts[0]

    # Must start with SELECT or WITH
    first_token_match = re.match(r"^([a-zA-Z]+)", statement)
    if not first_token_match:
        raise ReadOnlySecurityError("Security Error: Missing or invalid statement keyword.")

    first_token = first_token_match.group(1).lower()
    if first_token not in ("select", "with"):
        raise ReadOnlySecurityError(
            f"Security Error: Only SELECT queries are permitted. Found statement starting with '{first_token.upper()}'."
        )

    # Scan word boundaries for forbidden keywords
    tokens = set(re.findall(r"\b([a-zA-Z_]+)\b", statement.lower()))
    forbidden_found = tokens.intersection(FORBIDDEN_KEYWORDS)
    if forbidden_found:
        raise ReadOnlySecurityError(
            f"Security Error: Forbidden keyword(s) detected: {', '.join(sorted(forbidden_found)).upper()}."
        )


def execute_sql(
    query: str,
    db_path: Optional[str] = None,
    max_rows: int = 25,
) -> Dict[str, Any]:
    """Safely executes a read-only SELECT SQL query against the SQLite database.
    
    Returns:
        dict: {"success": True, "data": [...], "row_count": int, "columns": [...], "truncated": bool}
              or {"success": False, "error": str}
    """
    target_db = os.path.abspath(db_path or DEFAULT_DB_PATH)
    if not os.path.exists(target_db):
        return {"success": False, "error": f"Database file not found at {target_db}"}

    try:
        validate_read_only_sql(query)
    except ReadOnlySecurityError as e:
        return {"success": False, "error": str(e)}

    conn = None
    try:
        conn = get_read_only_connection(target_db)
        cur = conn.cursor()
        cur.execute(query)

        columns = [col[0] for col in cur.description] if cur.description else []
        rows = cur.fetchmany(max_rows + 1)

        truncated = len(rows) > max_rows
        actual_rows = rows[:max_rows]
        data = [dict(zip(columns, row)) for row in actual_rows]

        return {
            "success": True,
            "data": data,
            "row_count": len(data),
            "columns": columns,
            "truncated": truncated,
        }
    except sqlite3.Error as e:
        return {"success": False, "error": f"SQLite Error: {str(e)}"}
    except Exception as e:
        return {"success": False, "error": f"Execution Error: {str(e)}"}
    finally:
        if conn:
            conn.close()
