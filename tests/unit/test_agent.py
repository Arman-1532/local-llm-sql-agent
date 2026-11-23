"""Unit tests for Agent loop controls and LLM client."""

import pytest
from local_sql_agent.agent.agent import SQLAgent, run_agent
from local_sql_agent.database.builder import build_database
from local_sql_agent.llm.ollama_client import BudgetCapExceededError, OllamaClient


@pytest.fixture(scope="module")
def db_path(tmp_path_factory):
    fn = tmp_path_factory.mktemp("agent_data") / "test_unit_agent.db"
    build_database(str(fn), seed=42)
    return str(fn)


def test_agent_success_with_tools(db_path):
    """Test that agent calls execute_sql and returns 'ok' status."""
    step = 0

    def mock_backend(payload):
        nonlocal step
        step += 1
        if step == 1:
            return {
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [{
                        "id": "call_1",
                        "function": {
                            "name": "execute_sql",
                            "arguments": {"query": "SELECT COUNT(*) as count FROM customers"},
                        },
                    }],
                },
                "prompt_eval_count": 80,
                "eval_count": 20,
            }
        else:
            return {
                "message": {
                    "role": "assistant",
                    "content": "There are 50 customers in the database.",
                },
                "prompt_eval_count": 120,
                "eval_count": 15,
            }

    client = OllamaClient(model="mock-qwen", backend=mock_backend)
    result = run_agent("How many customers are there?", lm=client, db_path=db_path, max_steps=5)

    assert result.status == "ok"
    assert "50" in result.final_answer
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0]["tool"] == "execute_sql"
    assert len(result.sql_queries) == 1
    assert result.steps_taken == 2


def test_agent_step_cap(db_path):
    """Test that agent terminates with 'step_cap' if loop reaches max_steps."""
    def endless_backend(payload):
        return {
            "message": {
                "role": "assistant",
                "content": "",
                "tool_calls": [{
                    "id": "loop_call",
                    "function": {
                        "name": "execute_sql",
                        "arguments": {"query": "SELECT 1"},
                    },
                }],
            },
            "prompt_eval_count": 50,
            "eval_count": 10,
        }

    client = OllamaClient(model="mock-qwen", backend=endless_backend)
    result = run_agent("Test endless loop", lm=client, db_path=db_path, max_steps=3)

    assert result.status == "step_cap"
    assert result.steps_taken == 3
    assert "step limit" in result.final_answer.lower()


def test_agent_error_recovery(db_path):
    """Test that if a tool fails with SQL error, the agent receives the error and self-corrects."""
    call_idx = 0

    def retry_backend(payload):
        nonlocal call_idx
        call_idx += 1
        if call_idx == 1:
            return {
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [{
                        "id": "bad_call",
                        "function": {
                            "name": "execute_sql",
                            "arguments": {"query": "SELECT FROM customers"},
                        },
                    }],
                },
                "prompt_eval_count": 50,
                "eval_count": 10,
            }
        elif call_idx == 2:
            messages = payload.get("messages", [])
            assert any("syntax error" in str(m.get("content", "")).lower() for m in messages)
            return {
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [{
                        "id": "good_call",
                        "function": {
                            "name": "execute_sql",
                            "arguments": {"query": "SELECT COUNT(*) as cnt FROM customers"},
                        },
                    }],
                },
                "prompt_eval_count": 80,
                "eval_count": 15,
            }
        else:
            return {
                "message": {
                    "role": "assistant",
                    "content": "There are 50 customers.",
                },
                "prompt_eval_count": 100,
                "eval_count": 10,
            }

    client = OllamaClient(model="mock-qwen", backend=retry_backend)
    result = run_agent("Count customers with retry", lm=client, db_path=db_path, max_steps=5)

    assert result.status == "ok"
    assert len(result.tool_calls) == 2
    assert "syntax error" in str(result.tool_calls[0]["result"]).lower()
    assert result.tool_calls[1]["result"]["success"] is True


def test_agent_budget_cap(db_path):
    """Test that agent halts with 'budget_cap' status when budget is exceeded."""
    def expensive_backend(payload):
        return {
            "message": {
                "role": "assistant",
                "content": "",
                "tool_calls": [{
                    "id": "c1",
                    "function": {"name": "execute_sql", "arguments": {"query": "SELECT 1"}},
                }],
            },
            "prompt_eval_count": 1000,
            "eval_count": 500,
        }

    client = OllamaClient(model="mock-qwen", budget_cap_dollars=0.0001, backend=expensive_backend)
    result = run_agent("Test budget cap", lm=client, db_path=db_path, max_steps=5)

    assert result.status == "budget_cap"
    assert "budget cap" in result.final_answer.lower()
