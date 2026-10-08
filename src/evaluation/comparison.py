"""Operational comparison with explicit missingness; no automatic scientific scores."""

from collections import Counter, defaultdict
from statistics import median


def summarize_results(records):
    groups = defaultdict(list)
    for row in records:
        groups[row["arm"]].append(row)
    summaries = {}
    for arm, rows in groups.items():
        requests = [r for r in rows if r["result"]["request_sent"]]
        timings = [r["result"]["elapsed_seconds"] for r in requests]
        usage = {}
        for key in ["prompt_tokens", "completion_tokens", "total_tokens"]:
            values = [
                r["result"]["usage"][key]
                for r in requests
                if key in r["result"]["usage"]
            ]
            usage[key] = {
                "reported_sum": sum(values) if values else None,
                "reported_requests": len(values),
                "missing_requests": len(requests) - len(values),
            }
        stats = [
            r["citation_statistics"]
            for r in rows
            if r.get("citation_statistics") is not None
        ]
        markers = sum(s["marker_occurrences"] for s in stats)
        valid = sum(s["resolved_marker_occurrences"] for s in stats)
        chunk_ratios = [
            s["context_chunk_utilization"]
            for s in stats
            if s["context_chunk_utilization"] is not None
        ]
        by_question = defaultdict(list)
        for row in rows:
            if row["result"]["status"] == "success":
                by_question[row["question_id"]].append(row["answer"])
        summaries[arm] = {
            "records": len(rows),
            "statuses": dict(Counter(r["result"]["status"] for r in rows)),
            "sent_requests": len(requests),
            "usage": usage,
            "api_elapsed_seconds_median": median(timings) if timings else None,
            "api_elapsed_seconds_total": sum(timings) if timings else None,
            "full_end_to_end_seconds": None,
            "structural_marker_occurrences": markers if stats else None,
            "structural_marker_resolution_rate": valid / markers if markers else None,
            "context_chunk_utilization_mean": sum(chunk_ratios) / len(chunk_ratios)
            if chunk_ratios
            else None,
            "citation_statistics_records": len(stats),
            "successful_answer_uniqueness_by_question": {
                qid: {
                    "successful_repetitions": len(answers),
                    "distinct_exact_answers": len(set(answers)),
                }
                for qid, answers in by_question.items()
            },
            "scientific_quality_scores": None,
            "cost": None,
        }
    return {
        "schema": "chemqa-q10b-operational-summary-v1",
        "arms": summaries,
        "scientific_review_status": "pending_human_review",
        "cost_status": "price_unverified",
        "timing_scope": "API only; retrieval not timed in the frozen preview",
        "production_default_switched": False,
    }
