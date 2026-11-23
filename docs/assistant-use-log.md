# AI Assistant Use Log (Lab Rule Compliance)

This log adheres to the Course Lab Rule:
*Rule: Write test first (Red), watch it fail, write minimal code to pass (Green), then refactor. For each component, record a 3-line log: what it wrote, which test proves it, and what was reviewed.*

---

### Entry 1: Seeded SQLite Database Builder
- **What it wrote**: `src/local_sql_agent/database/builder.py` and `src/local_sql_agent/database/schema.sql` - deterministic generation of 4 relational tables (`customers`, `products`, `orders`, `order_items` with 300 rows in `order_items`) using fixed random seed 42.
- **Which test proves it**: `tests/integration/test_agent_integration.py` (`test_database_determinism`, `test_database_scale`).
- **What was reviewed**: Verified table relations, foreign keys, row counts (>100 in largest table), and confirmed byte-for-byte deterministic reproducibility across multiple builds.

---

### Entry 2: Read-Only Safety and Tool Infrastructure
- **What it wrote**: `src/local_sql_agent/tools/sql_executor.py` - read-only SQL validator, SQLite URI `mode=ro` connection handler, multi-statement injection blocker, row limiter, and schema introspection tool.
- **Which test proves it**: `tests/unit/test_sql_executor.py` (9 dangerous DDL/DML rejection tests, multi-statement rejection, row limit enforcement) and `tests/unit/test_sql_generator.py` (schema introspection and error reporting).
- **What was reviewed**: Tested against SQL injection variants, verified that destructive statements (DROP, DELETE, UPDATE, INSERT) and semicolon chaining are rejected before database access, and verified URI read-only failsafe.

---

### Entry 3: LLM Client with Cost Ledger, Cache, and Budget Cap
- **What it wrote**: `src/local_sql_agent/llm/ollama_client.py` - local Ollama HTTP client with SHA-256 parameter-keyed reply cache, per-call token ledger recording prompt and completion counts, and pre-execution budget cap enforcement.
- **Which test proves it**: `tests/unit/test_agent.py` (`test_agent_budget_cap`, `test_agent_success_with_tools`).
- **What was reviewed**: Verified ledger JSONL recording, verified that identical requests hit memory cache without network calls, and verified that calls over the configured budget cap are strictly refused with `BudgetCapExceededError`.

---

### Entry 4: Custom ReAct Agent Loop
- **What it wrote**: `src/local_sql_agent/agent/agent.py` - custom ReAct reasoning loop (no external SDKs) featuring step cap tracking, status reporting (`ok`, `step_cap`, `budget_cap`, `error`), tool execution dispatcher, error observation reflection, and dual-mode prompt templates.
- **Which test proves it**: `tests/unit/test_agent.py` (`test_agent_success_with_tools`, `test_agent_step_cap`, `test_agent_error_recovery`, `test_agent_budget_cap`).
- **What was reviewed**: Verified state transitions, step cap termination at `max_steps`, error propagation to assistant messages enabling self-correction, and final answer extraction.

---

### Entry 5: Evaluation Harness & Benchmark Test Set
- **What it wrote**: `src/local_sql_agent/evaluation/questions.py` (16 test questions across simple, joins, grouping, calculation, multi-tool, and unanswerable categories with independent SQL ground truth), `expected_answers.py`, `metrics.py`, and `evaluator.py` (3-trial evaluator measuring pass@1 and pass^3).
- **Which test proves it**: Programmatic evaluation execution across 48 runs per configuration against `store.db` ground truth values.
- **What was reviewed**: Inspected ground truth SQL queries for accuracy, checked pass@1 and pass^3 calculation formulas, and verified that run records capture timestamps, tool calls, SQL text, tokens, and latency.

---

### Entry 6: Bonus Implementation - Larger Model Comparison
- **What it wrote**: Evaluator model comparison support, `logs/run_log_gemma3.jsonl`, and `reports/results_gemma3.json` benchmarking `qwen2.5:3b` (3B) vs `gemma3:4b-it-qat` (4B) across all 16 questions.
- **Which test proves it**: Comparative execution runs on the benchmark test set and `tests/unit/test_sql_executor.py` verifying SQL calculation expressions.
- **What was reviewed**: Evaluated tool execution traces and final text completions for both models; analyzed the contrast between Qwen's faithful tool grounding (100% pass^3) vs Gemma 3's post-tool hallucination (6.25% pass^3).
