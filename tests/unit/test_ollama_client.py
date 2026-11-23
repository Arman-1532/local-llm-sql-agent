"""Unit tests for Ollama client: ledger, reply cache, and budget cap."""

import json
import pytest
from local_sql_agent.llm.ollama_client import BudgetCapExceededError, OllamaClient


def fake_backend(payload):
    return {
        "message": {"role": "assistant", "content": "Echo"},
        "prompt_eval_count": 50,
        "eval_count": 25,
        "done": True,
    }


def test_ledger_records_call(tmp_path):
    ledger_file = tmp_path / "ledger.jsonl"
    client = OllamaClient(
        model="qwen2.5:3b",
        ledger_path=str(ledger_file),
        backend=fake_backend,
    )

    resp = client.chat(messages=[{"role": "user", "content": "Hello"}])
    assert resp["message"]["content"] == "Echo"

    assert len(client.ledger) == 1
    entry = client.ledger[0]
    assert entry.prompt_tokens == 50
    assert entry.completion_tokens == 25
    assert entry.total_tokens == 75
    assert entry.cached is False
    assert entry.cost > 0.0


def test_reply_cache_hit(tmp_path):
    call_count = 0

    def counting_backend(payload):
        nonlocal call_count
        call_count += 1
        return {
            "message": {"role": "assistant", "content": f"Call {call_count}"},
            "prompt_eval_count": 40,
            "eval_count": 10,
        }

    client = OllamaClient(
        model="qwen2.5:3b",
        enable_cache=True,
        ledger_path=str(tmp_path / "ledger.jsonl"),
        backend=counting_backend,
    )

    resp1 = client.chat(messages=[{"role": "user", "content": "Test"}])
    assert call_count == 1
    assert resp1["message"]["content"] == "Call 1"

    resp2 = client.chat(messages=[{"role": "user", "content": "Test"}])
    assert call_count == 1  # backend not called again
    assert resp2["message"]["content"] == "Call 1"
    assert client.ledger[-1].cached is True


def test_budget_cap_refusal(tmp_path):
    client = OllamaClient(
        model="qwen2.5:3b",
        budget_cap_dollars=0.00001,
        ledger_path=str(tmp_path / "ledger.jsonl"),
        backend=fake_backend,
    )

    client.chat(messages=[{"role": "user", "content": "Call 1"}])

    with pytest.raises(BudgetCapExceededError):
        client.chat(messages=[{"role": "user", "content": "Call 2"}])
