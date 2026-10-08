"""Versioned evidence data supplied to generation, with canonical citation markers."""

import json
from pathlib import Path

from src.knowledge_base.identity import unique_chunks

CONTEXT_VERSION = "chemqa-evidence-v1"


def normalize_context(context: list[dict] | None) -> list[dict]:
    if context is None:
        return []
    if not isinstance(context, list) or any(
        not isinstance(item, dict) for item in context
    ):
        raise TypeError(
            "Evidence context must be a list of chunk dictionaries or None; raw strings are not supported"
        )
    return unique_chunks(context)


def serialize_context(context: list[dict] | None) -> str:
    chunks = normalize_context(context)
    evidence = []
    for chunk in chunks:
        status = chunk.get("location_status", "unavailable")
        item = {
            "citation": f"[Ref {chunk['chunk_id']}]",
            "chunk_id": chunk["chunk_id"],
            "doc_id": chunk["doc_id"],
            "source_title": chunk.get("title") or Path(chunk["source"]).name,
            "location_status": status,
            "page_numbers": chunk.get("page_numbers", [])
            if status == "located"
            else [],
            "text": chunk["text"],
        }
        if status == "unavailable":
            item["location_reason"] = chunk.get(
                "location_reason", "page_text_not_supplied"
            )
        evidence.append(item)
    return json.dumps(
        {
            "context_version": CONTEXT_VERSION,
            "evidence_count": len(evidence),
            "evidence": evidence,
        },
        ensure_ascii=False,
        indent=2,
    )
