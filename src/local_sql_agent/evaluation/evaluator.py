"""Evaluator module.
Coordinates execution of benchmark evaluations across trials, logs individual traces,
and generates summary metric reports.
"""

import json
import os
import time
from typing import Any, Dict, List, Optional

from local_sql_agent.agent.agent import SQLAgent
from local_sql_agent.evaluation.expected_answers import check_answer_correctness
from local_sql_agent.evaluation.metrics import calculate_benchmark_metrics
from local_sql_agent.evaluation.questions import BENCHMARK_QUESTIONS
from local_sql_agent.llm.ollama_client import OllamaClient

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../"))
DEFAULT_LOG_FILE = os.path.join(_PROJECT_ROOT, "logs", "run_log.jsonl")
DEFAULT_RESULTS_FILE = os.path.join(_PROJECT_ROOT, "reports", "results.json")


def run_benchmark(
    model: str = "qwen2.5:3b",
    trials: int = 3,
    max_steps: int = 6,
    log_file: Optional[str] = None,
    results_file: Optional[str] = None,
    temperature: float = 0.0,
    db_path: Optional[str] = None,
    tag: str = "main",
    mode: str = "improved",
) -> Dict[str, Any]:
    """Runs full benchmark evaluation across questions and trials."""
    log_path = os.path.abspath(log_file or DEFAULT_LOG_FILE)
    res_path = os.path.abspath(results_file or DEFAULT_RESULTS_FILE)

    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    os.makedirs(os.path.dirname(res_path), exist_ok=True)

    print("=" * 60)
    print(f"Starting Evaluation: model={model}, trials={trials}, tag={tag}, mode={mode}")
    print(f"Total questions: {len(BENCHMARK_QUESTIONS)} (Total runs: {len(BENCHMARK_QUESTIONS) * trials})")
    print("=" * 60)

    # Check for existing runs to support resume
    existing_runs_map = {}
    if os.path.exists(log_path):
        with open(log_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        rec = json.loads(line)
                        k = (rec.get("tag", tag), rec.get("question_id"), rec.get("trial"))
                        existing_runs_map[k] = rec
                    except Exception:
                        pass

    client = OllamaClient(model=model, enable_cache=False)
    agent = SQLAgent(llm=client, db_path=db_path, max_steps=max_steps, mode=mode)

    all_runs: List[Dict[str, Any]] = []
    question_results: Dict[str, List[bool]] = {q["id"]: [] for q in BENCHMARK_QUESTIONS}

    for q_idx, q_item in enumerate(BENCHMARK_QUESTIONS, start=1):
        qid = q_item["id"]
        q_text = q_item["question"]
        print(f"\n[{q_idx}/{len(BENCHMARK_QUESTIONS)}] {qid} ({q_item['category']}): {q_text}")

        for trial in range(1, trials + 1):
            key = (tag, qid, trial)
            if key in existing_runs_map:
                run_record = existing_runs_map[key]
                all_runs.append(run_record)
                is_correct = run_record["is_correct"]
                question_results[qid].append(is_correct)
                symbol = "✓" if is_correct else "✗"
                print(f"  Trial {trial}/{trials}: {symbol} [CACHED RUN] status={run_record['status']}, steps={run_record['steps_taken']}, time={run_record.get('latency_seconds', 0)}s")
                continue

            seed = 42 + trial * 10
            t_start = time.time()
            result = agent.run(question=q_text, temperature=temperature, seed=seed)
            elapsed = time.time() - t_start

            is_correct = check_answer_correctness(q_item, result.final_answer, result.tool_calls)
            question_results[qid].append(is_correct)

            run_record = {
                "tag": tag,
                "question_id": qid,
                "category": q_item["category"],
                "question": q_text,
                "trial": trial,
                "seed": seed,
                "status": result.status,
                "is_correct": is_correct,
                "tool_calls": result.tool_calls,
                "sql_queries": result.sql_queries,
                "final_answer": result.final_answer,
                "steps_taken": result.steps_taken,
                "prompt_tokens": result.prompt_tokens,
                "completion_tokens": result.completion_tokens,
                "total_tokens": result.total_tokens,
                "cost_dollars": result.cost_dollars,
                "latency_seconds": result.latency_seconds,
                "wall_time": round(elapsed, 4),
            }

            all_runs.append(run_record)

            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(run_record) + "\n")

            symbol = "✓" if is_correct else "✗"
            print(f"  Trial {trial}/{trials}: {symbol} status={result.status}, steps={result.steps_taken}, tokens={result.total_tokens}, time={result.latency_seconds:.2f}s")

    summary = calculate_benchmark_metrics(
        question_results=question_results,
        all_runs=all_runs,
        model_name=model,
        tag=tag,
        trials=trials,
    )

    with open(res_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print("\n=================== EVALUATION SUMMARY ===================")
    print(f"Model: {model} (Tag: {tag})")
    print(f"pass@1 (Average single run success): {summary.get('pass@1')}%")
    print(f"pass@3 (At least 1 of 3 succeeded): {summary.get('pass@3')}%")
    print(f"pass^3 (ALL 3 trials succeeded):    {summary.get('pass^3')}%")
    print(f"Total tokens consumed: {summary.get('total_tokens')}")
    print(f"Total cost: ${summary.get('total_cost_usd', 0.0):.6f}")
    print(f"Average latency per run: {summary.get('avg_latency_seconds')}s")
    print(f"Results written to: {res_path}")
    print("==========================================================")

    return summary
