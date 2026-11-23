"""Ollama Client and LLM Wrapper Module.
Features:
- Local Ollama communication for qwen2.5:3b (and other models).
- SHA-256 reply cache.
- Per-call token ledger recording prompt and completion tokens, latency, and notional USD cost.
- Pre-call budget cap refusal guard.
- Automatic fallback for models without native tool calling.
"""

import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from typing import Any, Callable, Dict, List, Optional


class BudgetCapExceededError(Exception):
    """Raised when cumulative token cost reaches or exceeds the configured budget cap."""
    pass


class LMCallError(Exception):
    """Raised when an error occurs during an LLM invocation."""
    pass


# Notional pricing per million tokens ($/1M tokens) per course specifications
PRICE_INPUT_PER_MILLION = 0.15   # $0.15 / 1M prompt tokens
PRICE_OUTPUT_PER_MILLION = 0.60  # $0.60 / 1M completion tokens


@dataclass
class LedgerEntry:
    timestamp: float
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost: float
    cached: bool
    latency_seconds: float
    prompt_summary: str


class OllamaClient:
    def __init__(
        self,
        model: str = "qwen2.5:3b",
        ollama_url: str = "http://127.0.0.1:11434",
        budget_cap_dollars: Optional[float] = None,
        token_cap: Optional[int] = None,
        enable_cache: bool = True,
        ledger_path: Optional[str] = None,
        backend: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
        supports_native_tools: bool = True,
    ):
        self.model = model
        self.ollama_url = ollama_url.rstrip("/")
        self.budget_cap_dollars = budget_cap_dollars
        self.token_cap = token_cap
        self.enable_cache = enable_cache
        self.ledger_path = ledger_path
        self.backend = backend
        self.supports_native_tools = supports_native_tools

        self.cache: Dict[str, Dict[str, Any]] = {}
        self.ledger: List[LedgerEntry] = []
        self.cumulative_cost: float = 0.0
        self.cumulative_tokens: int = 0

    def _compute_cache_key(self, payload: Dict[str, Any]) -> str:
        serialized = json.dumps(payload, sort_keys=True)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def _calculate_cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        in_cost = (prompt_tokens / 1_000_000.0) * PRICE_INPUT_PER_MILLION
        out_cost = (completion_tokens / 1_000_000.0) * PRICE_OUTPUT_PER_MILLION
        return in_cost + out_cost

    def _record_ledger(
        self,
        prompt_tokens: int,
        completion_tokens: int,
        cached: bool,
        latency: float,
        prompt_summary: str,
    ) -> LedgerEntry:
        cost = self._calculate_cost(prompt_tokens, completion_tokens) if not cached else 0.0
        entry = LedgerEntry(
            timestamp=time.time(),
            model=self.model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            cost=cost,
            cached=cached,
            latency_seconds=round(latency, 4),
            prompt_summary=prompt_summary,
        )
        self.ledger.append(entry)
        self.cumulative_cost += cost
        self.cumulative_tokens += (prompt_tokens + completion_tokens)

        if self.ledger_path:
            os.makedirs(os.path.dirname(os.path.abspath(self.ledger_path)), exist_ok=True)
            with open(self.ledger_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(asdict(entry)) + "\n")

        return entry

    def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.0,
        top_p: float = 0.9,
        top_k: int = 40,
        seed: Optional[int] = 42,
        format: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Invokes the Ollama chat endpoint with budget verification, ledger logging, and caching."""
        # 1. Budget Cap check (checked before execution)
        if self.budget_cap_dollars is not None and self.cumulative_cost >= self.budget_cap_dollars:
            raise BudgetCapExceededError(
                f"Budget cap exceeded: ${self.cumulative_cost:.6f} >= ${self.budget_cap_dollars:.6f}"
            )
        if self.token_cap is not None and self.cumulative_tokens >= self.token_cap:
            raise BudgetCapExceededError(
                f"Token budget cap exceeded: {self.cumulative_tokens} >= {self.token_cap} tokens"
            )

        # 2. Build payload
        options: Dict[str, Any] = {
            "temperature": temperature,
            "top_p": top_p,
            "top_k": top_k,
        }
        if seed is not None:
            options["seed"] = seed

        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": options,
        }
        if tools and self.supports_native_tools:
            payload["tools"] = tools
        if format:
            payload["format"] = format

        cache_key = self._compute_cache_key(payload)
        prompt_summary = str(messages[-1].get("content", ""))[:60] if messages else ""

        # 3. Cache check
        if self.enable_cache and cache_key in self.cache:
            cached_data = self.cache[cache_key]
            self._record_ledger(
                prompt_tokens=cached_data.get("prompt_eval_count", 0),
                completion_tokens=cached_data.get("eval_count", 0),
                cached=True,
                latency=0.0001,
                prompt_summary=f"[CACHED] {prompt_summary}",
            )
            return cached_data

        # 4. Invoke backend
        start_time = time.time()
        if self.backend:
            response_data = self.backend(payload)
        else:
            url = f"{self.ollama_url}/api/chat"
            req_data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=req_data,
                headers={"Content-Type": "application/json"},
            )
            try:
                with urllib.request.urlopen(req, timeout=120.0) as resp:
                    response_data = json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                err_body = e.read().decode("utf-8", errors="ignore")
                # Auto-fallback if model does not support native tools
                if "does not support tools" in err_body and "tools" in payload:
                    self.supports_native_tools = False
                    del payload["tools"]
                    req_data = json.dumps(payload).encode("utf-8")
                    req = urllib.request.Request(url, data=req_data, headers={"Content-Type": "application/json"})
                    with urllib.request.urlopen(req, timeout=120.0) as resp:
                        response_data = json.loads(resp.read().decode("utf-8"))
                else:
                    raise LMCallError(f"HTTP Error {e.code} from Ollama: {err_body}")
            except urllib.error.URLError as e:
                raise LMCallError(f"Ollama connection error at {url}: {str(e)}")
            except Exception as e:
                raise LMCallError(f"Error calling model: {str(e)}")

        latency = time.time() - start_time
        prompt_tokens = response_data.get("prompt_eval_count", 0)
        completion_tokens = response_data.get("eval_count", 0)

        # Fallback estimation if eval counts were 0
        if prompt_tokens == 0:
            prompt_tokens = sum(len(str(m)) // 4 for m in messages)
        if completion_tokens == 0:
            content = response_data.get("message", {}).get("content", "")
            completion_tokens = max(1, len(content) // 4)

        # 5. Record to ledger
        self._record_ledger(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cached=False,
            latency=latency,
            prompt_summary=prompt_summary,
        )

        # 6. Save in cache
        if self.enable_cache:
            self.cache[cache_key] = response_data

        return response_data


# Alias for backward compatibility
LMWrapper = OllamaClient
