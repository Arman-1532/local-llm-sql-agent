"""Evaluation package for local_sql_agent."""

from local_sql_agent.evaluation.evaluator import run_benchmark
from local_sql_agent.evaluation.expected_answers import check_answer_correctness
from local_sql_agent.evaluation.metrics import calculate_benchmark_metrics
from local_sql_agent.evaluation.questions import BENCHMARK_QUESTIONS

__all__ = [
    "BENCHMARK_QUESTIONS",
    "check_answer_correctness",
    "calculate_benchmark_metrics",
    "run_benchmark",
]
