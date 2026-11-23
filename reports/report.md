# Evaluation Report: Local AI Agent with Qwen 2.5 (3B)

**Course**: Agentic Software Architecture (Part 1)  
**Model**: `qwen2.5:3b` (Qwen 2.5, 3 Billion parameters) served locally via Ollama  
**Hardware Profile**: macOS, 8 GB Unified Memory  
**Evaluation Dataset**: 16 questions across 6 analytical categories, 3 trials each (48 runs total per configuration)

---

## 1. System Architecture

The agent is built from scratch without any high-level agent frameworks (no LangChain, CrewAI, or LlamaIndex). It implements a custom **ReAct (Reasoning + Acting)** execution cycle governed by strict resource and safety constraints.

```
                  +----------------------------------------------+
                  |                 User Query                   |
                  +----------------------------------------------+
                                         |
                                         v
+---------------------------------------------------------------------------------+
|                               Agent Loop (loop.py)                              |
|                                                                                 |
|  Controls: Step Cap (max 6), Token/Budget Cap, Status: [ok|step_cap|error]      |
|                                                                                 |
|      +-------------------------------------------------------------------+      |
|      |               LM Wrapper & Ledger Layer (lm.py)                   |      |
|      |                                                                   |      |
|      |  - SHA-256 Reply Cache (model + prompt + seed + params)           |      |
|      |  - Cost Ledger (JSONL: prompt/completion tokens, latency, cost)   |      |
|      |  - Pre-call Budget Refusal Guard ($ / token threshold)            |      |
|      +-------------------------------------------------------------------+      |
|                                   ^             |                               |
|                     Prompt tokens |             | Completion (Tool call JSON)   |
|                                   |             v                               |
|                    +------------------------------------+                       |
|                    |  Local Ollama Engine (qwen2.5:3b)  |                       |
|                    +------------------------------------+                       |
|                                         |                                       |
|                                         v                                       |
|      +-------------------------------------------------------------------+      |
|      |                         Tools Layer (tools.py)                    |      |
|      |                                                                   |      |
|      |  1. execute_sql:                                                  |      |
|      |     - AST / Token Safety Check (Strictly single SELECT only)      |      |
|      |     - Rejects DROP, DELETE, UPDATE, INSERT, ALTER, semicolons     |      |
|      |     - SQLite URI Read-Only Mode (file:store.db?mode=ro)           |      |
|      |     - Result Row Truncation (LIMIT 25)                            |      |
|      |     - Computes math, percentages, differences, averages via SQL   |      |
|      |                                                                   |      |
|      |  2. get_database_schema: Table definitions & schema introspection |      |
|      +-------------------------------------------------------------------+      |
|                                         |                                       |
|                       Tool Observation (Rows / Error JSON)                      |
|                                         v                                       |
|                    Re-sent into message history for reflection                  |
+---------------------------------------------------------------------------------+
                                         |
                                         v
                  +----------------------------------------------+
                  |         Final Answer (Tool-Backed)           |
                  +----------------------------------------------+
```

### Architectural Design Choice: SQL Generation Strategy
We evaluated two design patterns for SQL generation:
1. **Separate SQL Tool Model Call**: A dedicated tool function that invokes another LLM sub-call to translate natural language into SQL.
2. **In-Prompt Schema Dispatch (Chosen)**: Providing the database schema and relational hints directly in the system prompt, allowing the agent to generate SQL directly as arguments to `execute_sql`.

**Why In-Prompt Schema Dispatch was chosen:**
On an 8 GB RAM local environment, nested model calls double prompt evaluation latency and token consumption. Because the whole history must be re-sent on every step (re-sending conversation history adds more input tokens on every turn: base tokens + history accumulation), in-prompt schema generation enables single-turn execution (a single direct tool call) for standard queries, achieving 4.75s latency per query compared to >30s with nested multi-model workflows.

---

## 2. Experimental Evaluation: Baseline vs. Improved

Each question was tested over **3 independent trials** with different seeds. Ground truth values were calculated independently using deterministic SQLite scripts.

| Metric | Baseline Configuration | Improved Configuration | Absolute Improvement |
| :--- | :---: | :---: | :---: |
| **Model** | `qwen2.5:3b` | `qwen2.5:3b` | Identical local model |
| **pass@1** (Single run average) | **62.5%** (30/48) | **100.0%** (48/48) | **+37.5%** |
| **pass^3** (All 3 runs succeed) | **62.5%** (10/16) | **100.0%** (16/16) | **+37.5%** |
| **pass@3** (At least 1 succeeds) | **62.5%** (10/16) | **100.0%** (16/16) | **+37.5%** |
| **Average Latency / Run** | **32.55s** | **4.75s** | **6.8× faster** |
| **Total Tokens Consumed** | 133,428 tokens | 134,196 tokens | Comparable budget |
| **Total Notional Cost** | $0.030768 | $0.022036 | Lower output cost |

### Metric Definitions
- **pass@1**: The arithmetic mean of single-trial success rates across all questions (the average pass rate across all questions).
- **pass^3**: The fraction of tasks where **all 3 consecutive trials succeeded** (meaning all 3 trials out of 3 attempts passed successfully). It measures true reliability without lucky guesses.

---

## 3. The Three Most Common Failure Types (with Concrete Examples)

Analysis of failure logs from the baseline run revealed three primary failure categories:

### Failure 1: Non-Aggregate Row Dumping & Context Exhaustion
- **Description**: The 3B model attempted to answer aggregation or extreme-value questions by running `SELECT *` or joining large tables without `GROUP BY` or `LIMIT 1`. SQLite returned tens of rows, filling the context window and causing 120s timeouts on local CPU/Metal.
- **Concrete Example (Q07)**:
  - *Question*: "Which product category generated the highest total revenue from completed orders?"
  - *Baseline SQL*: `SELECT * FROM orders JOIN order_items ON orders.order_id = order_items.order_id`
  - *Result*: Truncated payload of 25 rows sent into prompt; model attempted to manually sum items in text, exceeding the 120s timeout (`status=error`).

### Failure 2: Accidental Sub-Grouping in Aggregate Customer Queries
- **Description**: When computing total revenue across all completed orders for a single customer, the model mistakenly included `GROUP BY orders.order_id`. This split the customer's purchase history into multiple rows rather than returning a single aggregate sum. The model then took the first row as the answer.
- **Concrete Example (Q04)**:
  - *Question*: "What is the total revenue from completed orders for customer 12?"
  - *Baseline SQL*: `SELECT SUM(oi.quantity * oi.unit_price) FROM orders o JOIN order_items oi ON o.order_id = oi.order_id WHERE o.customer_id = 12 AND o.status = 'completed' GROUP BY o.order_id;`
  - *Returned Data*: `[{total_revenue: 37.98}, {total_revenue: 217.96}, {total_revenue: 294.95}]`
  - *Model Output*: "$37.98" (Actual total: $550.89).

### Failure 3: Tool-Skipping / Incomplete Denominator Hallucination
- **Description**: For ratio and percentage questions, small models frequently count only the numerator, skip querying the total denominator, and hallucinate a percentage.
- **Concrete Example (Q12)**:
  - *Question*: "What percentage of all orders have 'completed' status?"
  - *Baseline SQL*: `SELECT COUNT(*) FROM orders WHERE status = 'completed';` (returned 73).
  - *Model Output*: "Out of all orders, 73% have completed status." (Incorrect: 73 completed out of 120 total orders is 60.83%).

---

## 4. The Change Made to Improve Performance

To resolve these failures, we introduced a three-part structural improvement to the agent orchestration:

1. **Relational Schema Annotations**: Added explicit foreign key paths to the system prompt (`orders.order_id = order_items.order_id`) and noted that `unit_price` lives in `order_items`, not `orders`.
2. **Aggregate-First Query Directives**: Explicitly instructed the model to compute `SUM()`, `AVG()`, `COUNT()`, and `LIMIT 1` directly inside SQL rather than returning raw rows.
3. **Step-1 Tool Enforcement**: If the model emitted text rather than a tool call on step 1 for an answerable question, the loop nudged the model to query SQLite first before generating natural language.

### Before & After Comparison

```
Question Category            Baseline pass^3      Improved pass^3
Simple (Q01 - Q03)                100%                 100%
Joins (Q04 - Q06)                  67%                 100%
Grouping (Q07 - Q09)               33%                 100%
Calculation (Q10 - Q12)            67%                 100%
Multi-Tool (Q13 - Q14)             50%                 100%
Unanswerable (Q15 - Q16)           50%                 100%
--------------------------------------------------------------
Overall pass^3                   62.5%               100.0%
Average Run Latency             32.55s                4.75s (6.8x faster)
```

## 5. Bonus Section: Larger Model Comparison

### Empirical Comparison of `qwen2.5:3b` vs. Larger Model (`gemma3:4b-it-qat`)
We benchmarked `qwen2.5:3b` (3 Billion parameters) against a larger model available locally on the system, **`gemma3:4b-it-qat`** (4 Billion parameters, quantized instruction-tuned), across the exact same 16 questions under identical evaluation conditions.

| Metric | `qwen2.5:3b` (3B) | `gemma3:4b-it-qat` (4B) | Comparison Insight |
| :--- | :---: | :---: | :---: |
| **Model Size** | 3 Billion parameters (1.9 GB) | 4 Billion parameters (4.0 GB) | Gemma 3 is 33% larger in parameter count |
| **Native Tool Calling Support** | Supported out-of-the-box | Rejected by Ollama (`HTTP 400`) | Gemma 3 requires text fallback |
| **pass@1** | **100.0%** | **6.25%** | Qwen 2.5 is **16× more reliable** |
| **pass^3** | **100.0%** | **6.25%** | Qwen 2.5 achieves consistent pass^3 |
| **Average Latency / Run** | **4.75s** | **14.86s** | Qwen 2.5 is **3.1× faster** |
| **Tool Observation Grounding** | **Faithful**: States exact tool numbers | **Hallucinatory**: Disregards tool output | Gemma 3 hallucinates placeholder values |
| **Unanswerable Handling** | **Truthful**: Refuses to guess | **Confabulatory**: Fabricates fake data | Gemma 3 invents 12-month warranties |

### Key Architectural Takeaway
This experiment provides a compelling lesson for agentic systems: **A larger parameter count does not imply superior agent performance**. 
- While `gemma3:4b-it-qat` successfully generated valid SQL queries in step 1, its language decoder frequently ignored the tool observation returned in step 2 and hallucinated fictional numbers (e.g., claiming 157 customers when SQLite returned 50).
- In contrast, `qwen2.5:3b` demonstrates superior tool-use fine-tuning, strictly grounding its reasoning and final responses in tool observations while running 3× faster on local 8 GB RAM hardware.
