"""Structural citation accounting; scientific support always needs human review."""

from src.qa_system.evidence import resolve_citations


def citation_statistics(answer, context):
    resolved = resolve_citations(answer, context, allow_legacy=False)
    valid = sum(resolved["counts"].values())
    invalid = len(resolved["unresolved"])
    chunks = resolved["chunks"]
    cited = [c for c in chunks if c["chunk_id"] in resolved["counts"]]
    docs = {c["doc_id"] for c in chunks}
    return {
        "schema": "chemqa-citation-statistics-v2",
        "marker_occurrences": valid + invalid,
        "resolved_marker_occurrences": valid,
        "unresolved_marker_occurrences": invalid,
        "marker_resolution_rate": valid / (valid + invalid)
        if valid + invalid
        else None,
        "context_chunk_count": len(chunks),
        "cited_chunk_count": len(cited),
        "context_chunk_utilization": len(cited) / len(chunks) if chunks else None,
        "context_document_count": len(docs),
        "cited_document_count": len({c["doc_id"] for c in cited}),
        "context_document_utilization": len({c["doc_id"] for c in cited}) / len(docs)
        if docs
        else None,
        "unresolved": resolved["unresolved"],
        "claim_support_precision": None,
        "claim_citation_recall": None,
        "scientific_support_review_status": "pending_human_review",
    }
