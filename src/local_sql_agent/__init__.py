"""local_sql_agent package."""

from local_sql_agent.agent.agent import AgentResult, SQLAgent, run_agent
from local_sql_agent.database.builder import build_database
from local_sql_agent.llm.ollama_client import OllamaClient
from local_sql_agent.tools.sql_executor import execute_sql
from local_sql_agent.tools.sql_generator import get_database_schema

__version__ = "0.1.0"

__all__ = [
    "AgentResult",
    "SQLAgent",
    "run_agent",
    "build_database",
    "OllamaClient",
    "execute_sql",
    "get_database_schema",
]
