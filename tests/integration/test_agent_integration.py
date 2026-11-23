"""Integration tests for local_sql_agent end-to-end functionality."""

import os
import sqlite3
import pytest

from local_sql_agent.agent.agent import SQLAgent
from local_sql_agent.database.builder import build_database
from local_sql_agent.database.connection import get_read_only_connection
from local_sql_agent.tools.sql_executor import execute_sql


@pytest.fixture(scope="module")
def seeded_db(tmp_path_factory):
    fn = tmp_path_factory.mktemp("integ_data") / "integration_store.db"
    build_database(str(fn), seed=42)
    return str(fn)


def test_database_determinism(tmp_path):
    """Verifies that two databases generated with the same seed are identical."""
    p1 = tmp_path / "db1.db"
    p2 = tmp_path / "db2.db"
    build_database(str(p1), seed=42)
    build_database(str(p2), seed=42)

    conn1 = sqlite3.connect(str(p1))
    conn2 = sqlite3.connect(str(p2))

    for tbl in ["customers", "products", "orders", "order_items"]:
        r1 = conn1.execute(f"SELECT * FROM {tbl} ORDER BY 1").fetchall()
        r2 = conn2.execute(f"SELECT * FROM {tbl} ORDER BY 1").fetchall()
        assert r1 == r2, f"Discrepancy in table: {tbl}"

    conn1.close()
    conn2.close()


def test_database_scale(seeded_db):
    """Verifies required table counts and row volume (>100 rows in largest table)."""
    conn = get_read_only_connection(seeded_db)
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM order_items")
    assert cur.fetchone()[0] == 300  # Biggest table > 100

    cur.execute("SELECT COUNT(*) FROM orders")
    assert cur.fetchone()[0] == 120

    cur.execute("SELECT COUNT(*) FROM customers")
    assert cur.fetchone()[0] == 50

    cur.execute("SELECT COUNT(*) FROM products")
    assert cur.fetchone()[0] == 25

    conn.close()


def test_sql_calculation_accuracy(seeded_db):
    """Verifies that execute_sql accurately evaluates complex calculation queries."""
    # Test percentage calculation
    pct_query = "SELECT ROUND((COUNT(CASE WHEN status = 'completed' THEN 1 END) * 100.0) / COUNT(*), 2) as pct FROM orders"
    res = execute_sql(pct_query, db_path=seeded_db)
    assert res["success"] is True
    assert res["data"][0]["pct"] == 60.83

    # Test customer 12 revenue join
    rev_query = """
    SELECT ROUND(SUM(oi.quantity * oi.unit_price), 2) as total
    FROM orders o JOIN order_items oi ON o.order_id = oi.order_id
    WHERE o.customer_id = 12 AND o.status = 'completed'
    """
    res = execute_sql(rev_query, db_path=seeded_db)
    assert res["success"] is True
    assert res["data"][0]["total"] == 550.89
