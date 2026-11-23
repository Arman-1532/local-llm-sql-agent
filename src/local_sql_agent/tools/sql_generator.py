"""SQL Generator & Schema Introspection Tool.
Provides:
- Schema introspection from SQLite master table.
- SQL query generation utilities and tool schemas.
"""

import os
import re
import sqlite3
from typing import Any, Dict, List, Optional

from local_sql_agent.database.connection import DEFAULT_DB_PATH, get_read_only_connection


def get_database_schema(db_path: Optional[str] = None) -> str:
    """Returns the SQL schema structure of all non-system tables in the database."""
    target_db = os.path.abspath(db_path or DEFAULT_DB_PATH)
    if not os.path.exists(target_db):
        return f"Error: Database file not found at {target_db}"

    conn = get_read_only_connection(target_db)
    cur = conn.cursor()
    cur.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
    tables_sql = [row[0] for row in cur.fetchall() if row[0]]
    conn.close()

    return "\n\n".join(tables_sql)


def generate_sql_query(
    question: str,
    schema: Optional[str] = None,
    db_path: Optional[str] = None,
    llm: Optional[Any] = None,
) -> Dict[str, Any]:
    """Generates schema-aware guidance or metadata for a SQL query."""
    current_schema = schema or get_database_schema(db_path)
    if llm:
        prompt = f"Given this SQLite schema:\n{current_schema}\n\nWrite strictly a read-only SELECT SQL query to answer: {question}\nReturn only the raw SQL query."
        resp = llm.chat(messages=[{"role": "user", "content": prompt}], temperature=0.0)
        content = resp.get("message", {}).get("content", "").strip()
        clean_sql = re.sub(r"```(?:sql)?\s*(.*?)\s*```", r"\1", content, flags=re.DOTALL).strip()
        return {"question": question, "sql": clean_sql, "success": True}
    return {
        "question": question,
        "schema_available": bool(current_schema),
        "note": "SQL is generated directly as arguments to execute_sql via in-prompt dispatch.",
        "success": True,
    }


# Standard tool specifications for Ollama function calling
TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "execute_sql",
            "description": "Executes a read-only SQL SELECT query against the SQLite database and returns the rows as JSON. Accepts ONLY SELECT statements.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The SQL SELECT query to execute. Example: 'SELECT COUNT(*) FROM customers'",
                    }
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_database_schema",
            "description": "Returns the exact CREATE TABLE schema statements showing all table names, columns, data types, and foreign key relationships in the database.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
]
