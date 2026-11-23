#!/usr/bin/env python3
"""CLI script to run full benchmark evaluation."""

import argparse
import os
import sys

# Ensure src/ is on PYTHONPATH
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from local_sql_agent.evaluation.evaluator import (
    DEFAULT_LOG_FILE,
    DEFAULT_RESULTS_FILE,
    run_benchmark,
)


def main():
    parser = argparse.ArgumentParser(description="Run SQL Agent Benchmark Evaluation")
    parser.add_argument("--model", default="qwen2.5:3b", help="Ollama model tag")
    parser.add_argument("--trials", type=int, default=3, help="Number of trials per question")
    parser.add_argument("--tag", default="main", help="Tag for this evaluation run")
    parser.add_argument("--mode", default="improved", choices=["baseline", "improved"], help="Loop mode")
    parser.add_argument("--log_file", default=DEFAULT_LOG_FILE, help="Path to jsonl log file")
    parser.add_argument("--results_file", default=DEFAULT_RESULTS_FILE, help="Path to results json file")
    parser.add_argument("--temperature", type=float, default=0.0, help="Sampling temperature")
    args = parser.parse_args()

    run_benchmark(
        model=args.model,
        trials=args.trials,
        tag=args.tag,
        mode=args.mode,
        log_file=args.log_file,
        results_file=args.results_file,
        temperature=args.temperature,
    )


if __name__ == "__main__":
    main()
