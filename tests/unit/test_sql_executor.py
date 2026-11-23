"""Unit tests for SQL executor and read-only safety validation."""

import pytest
from local_sql_agent.database.builder import build_database
from local_sql_agent.tools.sql_executor import execute_sql, validate_read_only_sql, ReadOnlySecurityError


@pytest.fixture(scope="module")
def db_path(tmp_path_factory):
    fn = tmp_path_factory.mktemp("data") / "test_executor.db"
    build_database(str(fn), seed=42)
    return str(fn)


def test_select_allowed(db_path):
    """Legitimate SELECT query should succeed."""
    result = execute_sql("SELECT COUNT(*) as count FROM customers", db_path=db_path)
    assert result["success"] is True
    assert result["data"] == [{"count": 50}]
    assert result["row_count"] == 1


def test_with_cte_select_allowed(db_path):
    """Common Table Expression (WITH ... SELECT) should be allowed."""
    query = """
    WITH high_stock AS (
        SELECT name, stock_quantity FROM products WHERE stock_quantity > 100
    )
    SELECT COUNT(*) as high_stock_count FROM high_stock
    """
    result = execute_sql(query, db_path=db_path)
    assert result["success"] is True
    assert result["row_count"] == 1


@pytest.mark.parametrize("malicious_query", [
    "DROP TABLE customers;",
    "DELETE FROM orders WHERE order_id = 1;",
    "UPDATE products SET price = 0.0;",
    "INSERT INTO customers (customer_id, name, email, city, signup_date) VALUES (999, 'Hacker', 'h@h.com', 'Nowhere', '2025-01-01');",
    "ALTER TABLE customers ADD COLUMN secret TEXT;",
    "CREATE TABLE backdoor (id INT);",
    "ATTACH DATABASE ':memory:' AS evil;",
    "PRAGMA writable_schema = 1;",
    "REPLACE INTO products (product_id, name, category, price, stock_quantity) VALUES (1, 'Bad', 'Cat', 1.0, 1);"
])
def test_reject_dangerous_statements(db_path, malicious_query):
    """Forbidden DDL/DML statements must be rejected with security error."""
    result = execute_sql(malicious_query, db_path=db_path)
    assert result["success"] is False
    assert "Security Error" in result["error"] or "Only SELECT" in result["error"]


def test_reject_multi_statement_injection(db_path):
    """Multiple statements separated by semicolon must be strictly rejected."""
    query = "SELECT * FROM customers; DROP TABLE customers;"
    result = execute_sql(query, db_path=db_path)
    assert result["success"] is False
    assert "Multiple statements" in result["error"] or "Security Error" in result["error"]


def test_row_limit_applied(db_path):
    """Row limit must truncate results to max_rows."""
    result = execute_sql("SELECT * FROM order_items", db_path=db_path, max_rows=10)
    assert result["success"] is True
    assert result["row_count"] == 10
    assert len(result["data"]) == 10
    assert result.get("truncated") is True
