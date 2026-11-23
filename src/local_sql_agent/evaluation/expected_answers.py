"""Expected answers and verification logic for benchmark evaluation."""

from typing import Any, Dict, List, Optional


def check_answer_correctness(
    question_item: Dict[str, Any],
    final_answer: str,
    tool_calls: List[Dict[str, Any]],
) -> bool:
    """Verifies whether an agent run correctly answered the question based on ground truth and tool usage."""
    text = final_answer.lower()

    if question_item.get("unanswerable"):
        phrases = [
            "not available", "cannot", "does not contain", "no credit score", "no salary",
            "no information", "not found", "doesn't have", "not present", "not recorded",
            "not in the database", "no warranty", "none of the", "not provide", "not provided",
            "not include", "does not have", "no data", "cannot be answered"
        ]
        return any(p in text for p in phrases)

    # For answerable queries, the agent must have executed at least one tool
    if not tool_calls:
        return False

    keywords = question_item.get("keywords", [])
    for kw in keywords:
        if kw.lower() in text:
            return True

    return False
