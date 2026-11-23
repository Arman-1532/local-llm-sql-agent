# Local SQL Agent Assignment

An autonomous, framework-free AI agent powered by `qwen2.5:3b` running locally via Ollama. The agent answers calculation and analytical questions by generating read-only SQL queries and executing them against a deterministic SQLite database.

---

## Quickstart (Under 5 Commands)

```bash
# 1. Pull the model in Ollama (ensure Ollama is running)
ollama pull qwen2.5:3b

# 2. Build the deterministic SQLite database (seeded dummy data)
python3 scripts/build_database.py

# 3. Run all unit and integration tests (TDD verification)
python3 -m pytest

# 4. Ask a question interactively in the terminal
python3 scripts/run_agent.py

# 5. Run the 16-question benchmark evaluation (3 trials each = 48 runs)
python3 scripts/run_evaluation.py --trials 3
```

---

## Interactive Terminal Prompting

### Option A: Interactive Chat Mode (Ask questions one by one)
```bash
python3 scripts/run_agent.py
```
Type any question and the agent will display:
- The exact SQL query generated.
- The rows returned from SQLite.
- The tool-backed final answer.
- Execution metrics: steps, token count, cost, and latency.

### Option B: Quick Single-Prompt Execution
```bash
python3 scripts/run_agent.py "What is the total revenue from completed orders for customer 12?"
python3 scripts/run_agent.py "Which product category generated the highest total revenue?"
python3 scripts/run_agent.py "What percentage of all orders have completed status?"
python3 scripts/run_agent.py "What is the credit score and salary of customer 5?"
```

---

## Project Architecture

```
local_sql_agent_assignment/
│
├── src/
│   └── local_sql_agent/
│       ├── __init__.py
│       │
│       ├── agent/
│       │   ├── __init__.py
│       │   └── agent.py                  # Custom ReAct loop, step cap & status reporting
│       │
│       ├── llm/
│       │   ├── __init__.py
│       │   └── ollama_client.py          # Local Ollama client, cache, cost ledger & budget cap
│       │
│       ├── tools/
│       │   ├── __init__.py
│       │   ├── sql_generator.py          # Schema introspection & SQL generator tool
│       │   └── sql_executor.py           # Read-only SQL executor with AST safety checks
│       │
│       ├── database/
│       │   ├── __init__.py
│       │   ├── schema.sql                # DDL definitions (customers, products, orders, items)
│       │   ├── connection.py             # Read-only URI connection factory (file:store.db?mode=ro)
│       │   └── builder.py                # Deterministic seed generator (seed=42)
│       │
│       └── evaluation/
│           ├── __init__.py
│           ├── questions.py              # 16 benchmark questions across 6 categories
│           ├── expected_answers.py       # Ground truth SQL computation & verification logic
│           ├── evaluator.py              # 3-trial benchmark evaluation runner
│           └── metrics.py                # pass@1, pass@3, pass^3 and latency metrics
│
├── scripts/
│   ├── build_database.py                 # CLI to build/populate SQLite database
│   ├── run_agent.py                      # CLI for interactive chat or single query
│   └── run_evaluation.py                 # CLI to run benchmark evaluations
│
├── tests/
│   ├── unit/
│   │   ├── test_sql_executor.py          # Read-only safety, DDL/DML rejection & row limits
│   │   ├── test_sql_generator.py         # Schema introspection & query generation
│   │   ├── test_ollama_client.py         # Cache, cost ledger & budget cap refusal
│   │   └── test_agent.py                 # Step cap, budget cap & error recovery
│   │
│   └── integration/
│       └── test_agent_integration.py     # Deterministic build, table scaling & calculation tests
│
├── data/
│   ├── .gitkeep
│   └── store.db                          # Generated deterministic SQLite database
│
├── logs/
│   ├── .gitkeep
│   ├── run_log.jsonl                     # 48 run records for improved agent (100% pass^3)
│   ├── run_log_baseline.jsonl            # 48 run records for baseline agent (62.5% pass^3)
│   └── run_log_gemma3.jsonl              # Run records for larger model comparison (Gemma 3 4B)
│
├── reports/
│   ├── .gitkeep
│   ├── report.md                         # Formal 1-2 page evaluation report
│   ├── results.json                      # Summary metrics for improved agent
│   ├── results_baseline.json             # Summary metrics for baseline agent
│   └── results_gemma3.json               # Summary metrics for larger model comparison
│
├── docs/
│   ├── architecture.md                   # Full system architecture, terminology & Viva Q&A
│   ├── test-plan.md                      # TDD test strategy and test cases
│   └── assistant-use-log.md              # Required 3-line logs per component
│
├── requirements.txt
├── pyproject.toml
├── .gitignore
└── README.md
```

---

## Safety & Security Guarantees

1. **URI Read-Only Mode**: SQLite is accessed exclusively via URI `file:data/store.db?mode=ro`. File writes are blocked at the engine level.
2. **AST & Keyword Validation**: Rejects `DROP`, `DELETE`, `UPDATE`, `INSERT`, `ALTER`, `CREATE`, `ATTACH`, `PRAGMA`.
3. **Multi-Statement Blocking**: Semicolon-separated statement injection is immediately rejected.
4. **Row Truncation**: Capped at 25 rows (`max_rows=25`) to prevent prompt context bloat.
5. **No Hallucinated Calculations**: Calculations (totals, averages, counts, differences, percentages) are computed directly in SQL using SQL expressions.

---

## Experimental Results Summary

| Metric | Baseline Agent | Improved Agent | Larger Model (`gemma3:4b`) |
| :--- | :---: | :---: | :---: |
| **Model** | `qwen2.5:3b` | `qwen2.5:3b` | `gemma3:4b-it-qat` |
| **pass@1** | 62.5% | **100.0%** | 6.25% |
| **pass^3** | 62.5% | **100.0%** | 6.25% |
| **Average Latency** | 32.55s | **4.75s** | 14.86s |
| **Error / Timeouts** | 3 timeouts | **0 errors** | 0 errors |
