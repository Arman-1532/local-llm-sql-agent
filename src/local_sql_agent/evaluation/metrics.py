"""Metrics calculation module for agent evaluation."""

from typing import Any, Dict, List


def calculate_benchmark_metrics(
    question_results: Dict[str, List[bool]],
    all_runs: List[Dict[str, Any]],
    model_name: str,
    tag: str,
    trials: int,
) -> Dict[str, Any]:
    """Computes pass@1, pass@3, pass^3, latency, token consumption, and cost."""
    total_q = len(question_results)
    if total_q == 0:
        return {}

    pass_at_1_scores = [sum(scores) / len(scores) for scores in question_results.values() if scores]
    pass_at_1 = sum(pass_at_1_scores) / len(pass_at_1_scores) if pass_at_1_scores else 0.0

    pass_at_3_count = sum(1 for scores in question_results.values() if any(scores))
    pass_at_3 = pass_at_3_count / total_q

    pass_pow_3_count = sum(1 for scores in question_results.values() if len(scores) == trials and all(scores))
    pass_pow_3 = pass_pow_3_count / total_q

    total_tokens_all = sum(r.get("total_tokens", 0) for r in all_runs)
    total_cost_all = sum(r.get("cost_dollars", 0.0) for r in all_runs)
    avg_latency = (
        sum(r.get("latency_seconds", 0.0) for r in all_runs) / len(all_runs)
        if all_runs
        else 0.0
    )

    return {
        "model": model_name,
        "tag": tag,
        "trials": trials,
        "total_questions": total_q,
        "total_runs": len(all_runs),
        "pass@1": round(pass_at_1 * 100, 2),
        "pass@3": round(pass_at_3 * 100, 2),
        "pass^3": round(pass_pow_3 * 100, 2),
        "total_tokens": total_tokens_all,
        "total_cost_usd": round(total_cost_all, 6),
        "avg_latency_seconds": round(avg_latency, 2),
        "question_breakdown": {
            qid: {
                "trials": question_results[qid],
                "pass_rate": round(sum(question_results[qid]) / len(question_results[qid]) * 100, 1)
                if question_results[qid]
                else 0.0,
                "perfect_3_of_3": len(question_results[qid]) == trials and all(question_results[qid]),
            }
            for qid in question_results
        },
    }
