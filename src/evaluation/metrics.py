"""Metrics refer only to annotated sources; unjudged chunks are not negatives."""

from statistics import mean


def covered_characters(anchor, ranked):
    """Union matching page intervals; overlapping/repeated chunks count only once."""
    intervals = []
    for result in ranked:
        doc = result["document"]
        if (
            doc.get("doc_id") != anchor["doc_id"]
            or doc.get("location_status") != "located"
        ):
            continue
        for span in doc.get("source_spans", []):
            if span["page_number"] == anchor["page_number"]:
                start = max(anchor["char_start"], span["char_start"])
                end = min(anchor["char_end"], span["char_end"])
                if end > start:
                    intervals.append((start, end))
    covered, cursor = 0, anchor["char_start"]
    for start, end in sorted(intervals):
        covered += max(0, end - max(cursor, start))
        cursor = max(cursor, end)
    return covered


def retrieval_metrics(question, ranked, cutoffs=(1, 5, 10)):
    if question["answerability"] != "answerable":
        return None
    anchors = question["evidence"]
    required_docs = {anchor["doc_id"] for anchor in anchors}
    result = {"at_k": {}}
    first_doc = next(
        (
            rank
            for rank, hit in enumerate(ranked, 1)
            if hit["document"].get("doc_id") in required_docs
        ),
        None,
    )
    first_complete = None
    for rank in range(1, len(ranked) + 1):
        if any(
            covered_characters(anchor, ranked[:rank])
            == anchor["char_end"] - anchor["char_start"]
            for anchor in anchors
        ):
            first_complete = rank
            break
    result["rr_first_annotated_doc"] = 1 / first_doc if first_doc else 0.0
    result["rr_first_complete_anchor"] = 1 / first_complete if first_complete else 0.0
    for k in cutoffs:
        if type(k) is not int or k <= 0:
            raise ValueError("Cutoffs must be positive integers")
        hits = ranked[:k]
        found = {hit["document"].get("doc_id") for hit in hits} & required_docs
        coverage = {
            a["evidence_id"]: covered_characters(a, hits)
            / (a["char_end"] - a["char_start"])
            for a in anchors
        }
        complete = {eid for eid, fraction in coverage.items() if fraction == 1.0}
        result["at_k"][str(k)] = {
            "annotated_doc_hit": float(bool(found)),
            "annotated_doc_recall": len(found) / len(required_docs),
            "all_annotated_docs_hit": float(found == required_docs),
            "mean_anchor_character_coverage": mean(coverage.values()),
            "complete_anchor_recall": len(complete) / len(anchors),
            "all_anchors_complete": float(len(complete) == len(anchors)),
            "annotated_point_evidence_complete": mean(
                float(set(point["evidence_ids"]) <= complete)
                for point in question["answer_points"]
            ),
            "anchor_coverage": coverage,
        }
    return result


def aggregate_metrics(records, field):
    judged = [row[field] for row in records if row[field] is not None]
    if not judged:
        return {"scored_questions": 0, "metrics": None}
    return {
        "scored_questions": len(judged),
        "rr_first_annotated_doc": mean(row["rr_first_annotated_doc"] for row in judged),
        "rr_first_complete_anchor": mean(
            row["rr_first_complete_anchor"] for row in judged
        ),
        "at_k": {
            k: {
                metric: mean(row["at_k"][k][metric] for row in judged)
                for metric in judged[0]["at_k"][k]
                if metric != "anchor_coverage"
            }
            for k in judged[0]["at_k"]
        },
    }


def manual_review_template(questions):
    return {
        "schema": "chemqa-manual-review-v1",
        "status": "not_scored",
        "reviewer": None,
        "questions": [
            {
                "question_id": row["question_id"],
                "answer_run": None,
                "point_scores": [
                    {"point_id": point["point_id"], "score": None, "reason": None}
                    for point in row["answer_points"]
                ],
                "conditions_units_score": None,
                "system_boundary_score": None,
                "evidence_support_score": None,
                "citation_correspondence_score": None,
                "insufficiency_score": None,
                "unsupported_claims": None,
                "notes": None,
            }
            for row in questions
        ],
    }
