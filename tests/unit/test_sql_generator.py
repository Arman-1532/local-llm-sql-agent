"""Unit tests for SQL generator and schema introspection."""

from unittest.mock import MagicMock

import pytest
from local_sql_agent.database.builder import build_database
from local_sql_agent.tools.sql_executor import execute_sql
from local_sql_agent.tools.sql_generator import get_database_schema, generate_sql_query


@pytest.fixture(scope="module")
def db_path(tmp_path_factory):
    fn = tmp_path_factory.mktemp("gen_data") / "test_gen.db"
    build_database(str(fn), seed=42)
    return str(fn)


def test_get_database_schema(db_path):
    schema = get_database_schema(db_path=db_path)
    assert "customers" in schema
    assert "products" in schema
    assert "orders" in schema
    assert "order_items" in schema
    assert "customer_id" in schema
    assert "unit_price" in schema


def test_generate_sql_query_helper(db_path):
    res = generate_sql_query("How many orders?", db_path=db_path)
    assert res["question"] == "How many orders?"
    assert res["schema_available"] is True
    assert res["success"] is True


def test_generate_sql_query_with_llm(db_path):
    mock_llm = MagicMock()
    mock_llm.chat.return_value = {
        "message": {
            "content": "```sql\nSELECT COUNT(*) FROM orders;\n```"
        }
    }
    res = generate_sql_query("How many orders?", db_path=db_path, llm=mock_llm)
    assert res["success"] is True
    assert res["question"] == "How many orders?"
    assert res["sql"] == "SELECT COUNT(*) FROM orders;"
    mock_llm.chat.assert_called_once()


def test_sql_syntax_error_reporting(db_path):
    res = execute_sql("SELECT FROM customers", db_path=db_path)
    assert res["success"] is False
    assert "syntax error" in res["error"].lower()


def test_sql_nonexistent_column(db_path):
    res = execute_sql("SELECT fake_column FROM customers", db_path=db_path)
    assert res["success"] is False
    assert "no such column" in res["error"].lower()
