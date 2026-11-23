#!/usr/bin/env python3
"""CLI script to run the SQL agent interactively or with a single prompt."""

import os
import sys

# Ensure src/ is on PYTHONPATH
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from local_sql_agent.agent.agent import SQLAgent
from local_sql_agent.database.builder import build_database
from local_sql_agent.database.connection import DEFAULT_DB_PATH
from local_sql_agent.llm.ollama_client import OllamaClient


def format_currency(dollars: float) -> str:
    return f"${dollars:.6f}"


def run_single(agent: SQLAgent, question: str):
    print("\n" + "=" * 65)
    print(f"🤖 User Query: {question}")
    print("=" * 65)
    print("⏳ Agent is reasoning and querying database...\n")

    result = agent.run(question=question)

    if result.tool_calls:
        print("🔧 Tool Calls Executed:")
        for tc in result.tool_calls:
            step = tc.get("step")
            tool = tc.get("tool")
            args = tc.get("args", {})
            res = tc.get("result", {})
            print(f"  ▶ Step {step}: [{tool}]")
            if tool == "execute_sql":
                print(f"    SQL: {args.get('query')}")
                if res.get("success"):
                    print(f"    Rows ({res.get('row_count')}): {res.get('data')}")
                else:
                    print(f"    Error: {res.get('error')}")
            elif tool == "get_database_schema":
                print("    Retrieved database schema.")
            print()

    print("💬 Final Answer:")
    print("-" * 65)
    print(result.final_answer)
    print("-" * 65)
    print("📊 Run Metrics:")
    print(f"   Status:   {result.status.upper()}")
    print(f"   Steps:    {result.steps_taken}")
    print(f"   Tokens:   {result.total_tokens} (Prompt: {result.prompt_tokens}, Completion: {result.completion_tokens})")
    print(f"   Cost:     {format_currency(result.cost_dollars)}")
    print(f"   Latency:  {result.latency_seconds:.2f}s")
    print("=" * 65 + "\n")


def main():
    if not os.path.exists(DEFAULT_DB_PATH):
        print(f"Database not found at {DEFAULT_DB_PATH}. Building database with fixed seed...")
        build_database(DEFAULT_DB_PATH)

    client = OllamaClient(model="qwen2.5:3b")
    agent = SQLAgent(llm=client, db_path=DEFAULT_DB_PATH, mode="improved")

    if len(sys.argv) > 1:
        question = " ".join(sys.argv[1:])
        run_single(agent, question)
        return

    print("=" * 65)
    print("🤖 Local SQL Agent CLI (Model: qwen2.5:3b)")
    print("   Type your question, or 'exit' / 'quit' to stop.")
    print("=" * 65)
    print("\n💡 Sample queries to test:")
    print("   - How many customers are registered in the database?")
    print("   - What is the total revenue from completed orders for customer 12?")
    print("   - Which product category generated the highest total revenue?")
    print("   - What percentage of all orders have completed status?")
    print("   - What is the credit score and salary of customer 5?\n")

    while True:
        try:
            prompt = input("Ask a question > ").strip()
            if not prompt:
                continue
            if prompt.lower() in ("exit", "quit", "q"):
                print("Goodbye!")
                break
            run_single(agent, prompt)
        except (KeyboardInterrupt, EOFError):
            print("\nGoodbye!")
            break


if __name__ == "__main__":
    main()
