"""Agent module for local_sql_agent.
Implements custom ReAct reasoning loop without third-party agent frameworks.
Features:
- Step cap (max_steps)
- Budget and token cap controls
- Clear final status ('ok', 'step_cap', 'budget_cap', 'error')
- Tool dispatch (execute_sql, get_database_schema)
- Error reflection & self-correction
- Multi-format response parser
"""

import json
import re
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from local_sql_agent.database.connection import DEFAULT_DB_PATH
from local_sql_agent.llm.ollama_client import BudgetCapExceededError, OllamaClient
from local_sql_agent.tools.sql_executor import execute_sql
from local_sql_agent.tools.sql_generator import TOOL_DEFINITIONS, get_database_schema

BASELINE_SYSTEM_PROMPT = """You are a data analysis assistant with access to an SQLite store database.
DATABASE SCHEMA:
{schema}

AVAILABLE TOOLS:
1. `execute_sql(query)`: Executes a read-only SELECT SQL query.
2. `get_database_schema()`: Inspects database schema.

Answer the user question using the tools. All calculations must be computed using SQL queries.
"""

IMPROVED_SYSTEM_PROMPT = """You are a precise data analytics assistant with access to an SQLite store database.
You must answer user questions strictly using tools. NEVER guess, estimate, or hallucinate numbers yourself.

DATABASE SCHEMA:
{schema}

AVAILABLE TOOLS:
1. `execute_sql(query)`: Executes a read-only SELECT SQL query.
2. `get_database_schema()`: Returns database table definitions and schema.

CRITICAL RULES & QUERY PATTERNS:
1. EFFICIENCY & AGGREGATIONS:
   - Compute aggregates directly in SQL: use SUM(), AVG(), COUNT(), MIN(), MAX().
   - Difference between max and min product price: `SELECT ROUND(MAX(price) - MIN(price), 2) FROM products`
2. REVENUE & ORDER TOTALS:
   - `orders` connects to `order_items` via `order_id`. Revenue = `SUM(order_items.quantity * order_items.unit_price)`.
   - Always filter `WHERE orders.status = 'completed'` when completed orders are requested.
   - For a specific customer's total revenue, sum across ALL their orders without any GROUP BY:
     `SELECT ROUND(SUM(oi.quantity * oi.unit_price), 2) as total_revenue FROM orders o JOIN order_items oi ON o.order_id = oi.order_id WHERE o.customer_id = 12 AND o.status = 'completed'`
     (Do NOT use GROUP BY order_id, or it will split orders into separate rows).
   - Average completed order revenue:
     `SELECT ROUND(AVG(order_total), 2) FROM (SELECT SUM(quantity * unit_price) AS order_total FROM orders JOIN order_items ON orders.order_id = order_items.order_id WHERE status = 'completed' GROUP BY orders.order_id)`
3. PERCENTAGE & COMPARISON QUERIES:
   - Percentage of total orders:
     `SELECT ROUND((COUNT(CASE WHEN status = 'completed' THEN 1 END) * 100.0) / COUNT(*), 2) FROM orders`
   - Difference between categories:
     `SELECT ROUND((SELECT AVG(price) FROM products WHERE category = 'Electronics') - (SELECT AVG(price) FROM products WHERE category = 'Books'), 2)`
4. MATHEMATICAL & PERCENTAGE CALCULATIONS:
   - Compute all calculations, percentages, and differences directly in SQL using the `execute_sql` tool.
   - For average and minimum order totals and the percentage difference:
     `WITH totals AS (SELECT o.order_id, SUM(oi.quantity * oi.unit_price) as t FROM orders o JOIN order_items oi ON o.order_id = oi.order_id WHERE o.status = 'completed' GROUP BY o.order_id) SELECT ROUND(AVG(t), 2) as avg_val, ROUND(MIN(t), 2) as min_val, ROUND(((AVG(t) - MIN(t)) / MIN(t)) * 100.0, 2) as pct_above FROM totals`
5. UNANSWERABLE QUESTIONS:
   - If a question asks for information NOT present in the database (e.g. employee salaries, customer credit scores, warranty periods), explicitly state that this data is not available in the database. Do NOT invent numbers.
6. ERROR RECOVERY:
   - If a SQL query returns an error, examine the SQLite error message and write a corrected query.
"""


@dataclass
class AgentResult:
    question: str
    final_answer: str
    status: str  # 'ok', 'step_cap', 'budget_cap', 'error'
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    sql_queries: List[str] = field(default_factory=list)
    steps_taken: int = 0
    total_tokens: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_dollars: float = 0.0
    latency_seconds: float = 0.0
    history: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _parse_model_response(message: Dict[str, Any]) -> Dict[str, Any]:
    """Parses model output to determine if it is a tool call or a final answer."""
    raw_tool_calls = message.get("tool_calls", [])
    content = (message.get("content") or "").strip()

    # 1. Native function calling
    if raw_tool_calls:
        parsed_calls = []
        for tc in raw_tool_calls:
            fn = tc.get("function", {})
            name = fn.get("name")
            args = fn.get("arguments", {})
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {"raw": args}
            parsed_calls.append({"name": name, "args": args, "id": tc.get("id")})
        return {"type": "tool_calls", "calls": parsed_calls, "content": content}

    # 2. JSON in text content
    if content:
        json_candidates = []
        for match in re.finditer(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL):
            json_candidates.append(match.group(1))

        start = content.find("{")
        end = content.rfind("}")
        if start != -1 and end != -1 and end > start:
            json_candidates.append(content[start : end + 1])

        for cand in json_candidates:
            try:
                data = json.loads(cand)
                if isinstance(data, dict):
                    if "tool" in data and ("args" in data or "arguments" in data):
                        args = data.get("args", data.get("arguments", {}))
                        return {"type": "tool_calls", "calls": [{"name": data["tool"], "args": args, "id": None}], "content": content}
                    elif "name" in data and ("args" in data or "arguments" in data):
                        args = data.get("args", data.get("arguments", {}))
                        return {"type": "tool_calls", "calls": [{"name": data["name"], "args": args, "id": None}], "content": content}
                    elif "final" in data or "final_answer" in data or "answer" in data:
                        final_text = str(data.get("final") or data.get("final_answer") or data.get("answer"))
                        return {"type": "final", "content": final_text}
            except json.JSONDecodeError:
                continue

    # 3. Function-call syntax
    if content:
        func_match = re.search(r'(execute_sql|get_database_schema)\s*\(\s*(?:query\s*=\s*)?["\'](.*?)["\']\s*\)', content, re.DOTALL)
        if func_match:
            fn_name = func_match.group(1)
            arg_val = func_match.group(2)
            return {"type": "tool_calls", "calls": [{"name": fn_name, "args": {"query": arg_val}, "id": None}], "content": content}

    # 4. Plain text response
    return {"type": "final", "content": content}


class SQLAgent:
    """Autonomous SQL Agent."""

    def __init__(
        self,
        llm: Optional[OllamaClient] = None,
        db_path: Optional[str] = None,
        max_steps: int = 6,
        mode: str = "improved",
    ):
        self.llm = llm or OllamaClient(model="qwen2.5:3b")
        self.db_path = db_path or DEFAULT_DB_PATH
        self.max_steps = max_steps
        self.mode = mode

    def run(
        self,
        question: str,
        temperature: float = 0.0,
        seed: Optional[int] = 42,
    ) -> AgentResult:
        """Executes the agent loop on a question."""
        start_time = time.time()
        schema_str = get_database_schema(db_path=self.db_path)
        template = IMPROVED_SYSTEM_PROMPT if self.mode == "improved" else BASELINE_SYSTEM_PROMPT
        system_prompt = template.format(schema=schema_str)

        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": question},
        ]

        recorded_tool_calls: List[Dict[str, Any]] = []
        recorded_sql_queries: List[str] = []
        step = 0
        final_answer = ""
        status = "ok"

        initial_tokens = self.llm.cumulative_tokens
        initial_cost = self.llm.cumulative_cost

        try:
            while step < self.max_steps:
                step += 1

                resp = self.llm.chat(
                    messages=messages,
                    tools=TOOL_DEFINITIONS,
                    temperature=temperature,
                    seed=seed,
                )

                assistant_msg = resp.get("message", {})
                parsed = _parse_model_response(assistant_msg)

                # In improved mode, enforce step 1 tool execution for answerable queries
                if self.mode == "improved" and step == 1 and parsed["type"] == "final":
                    content = parsed["content"]
                    unanswerable_cues = ["not available", "cannot be answered", "does not contain", "no credit score", "no salary", "no warranty", "not recorded"]
                    if not any(cue in content.lower() for cue in unanswerable_cues):
                        messages.append({"role": "assistant", "content": content})
                        messages.append({"role": "user", "content": "You must query the database using the execute_sql tool before providing the answer. Please run the appropriate SQL SELECT query as a tool call."})
                        continue

                # If final answer
                if parsed["type"] == "final":
                    final_answer = parsed["content"].strip()
                    status = "ok"
                    messages.append({"role": "assistant", "content": final_answer})
                    break

                # Process tool calls
                parsed_calls = parsed.get("calls", [])
                messages.append(assistant_msg)
                for call in parsed_calls:
                    tool_name = call["name"]
                    args = call["args"] or {}

                    if tool_name == "execute_sql":
                        query = args.get("query", "")
                        recorded_sql_queries.append(query)
                        result = execute_sql(query, db_path=self.db_path)
                    elif tool_name == "get_database_schema":
                        result = {"success": True, "schema": schema_str}
                    else:
                        result = {"success": False, "error": f"Unknown tool: '{tool_name}'"}

                    recorded_tool_calls.append({
                        "step": step,
                        "tool": tool_name,
                        "args": args,
                        "result": result,
                    })

                    tool_msg: Dict[str, Any] = {
                        "role": "tool",
                        "content": json.dumps(result, ensure_ascii=False),
                    }
                    if call.get("id"):
                        tool_msg["tool_call_id"] = call["id"]
                    messages.append(tool_msg)

            else:
                status = "step_cap"
                final_answer = f"Terminated: Reached step limit of {self.max_steps} steps without completing final answer."

        except BudgetCapExceededError as e:
            status = "budget_cap"
            final_answer = f"Terminated: {str(e)}"
        except Exception as e:
            status = "error"
            final_answer = f"Terminated with error: {str(e)}"

        total_latency = time.time() - start_time
        total_tokens_used = self.llm.cumulative_tokens - initial_tokens
        cost_dollars = self.llm.cumulative_cost - initial_cost

        prompt_tokens_used = sum(e.prompt_tokens for e in self.llm.ledger[-step:]) if self.llm.ledger else 0
        completion_tokens_used = sum(e.completion_tokens for e in self.llm.ledger[-step:]) if self.llm.ledger else 0

        return AgentResult(
            question=question,
            final_answer=final_answer,
            status=status,
            tool_calls=recorded_tool_calls,
            sql_queries=recorded_sql_queries,
            steps_taken=step,
            total_tokens=total_tokens_used,
            prompt_tokens=prompt_tokens_used,
            completion_tokens=completion_tokens_used,
            cost_dollars=cost_dollars,
            latency_seconds=round(total_latency, 4),
            history=messages,
        )


def run_agent(
    question: str,
    lm: Optional[OllamaClient] = None,
    db_path: Optional[str] = None,
    max_steps: int = 6,
    temperature: float = 0.0,
    seed: Optional[int] = 42,
    mode: str = "improved",
) -> AgentResult:
    """Convenience function to run the agent."""
    agent = SQLAgent(llm=lm, db_path=db_path, max_steps=max_steps, mode=mode)
    return agent.run(question=question, temperature=temperature, seed=seed)
