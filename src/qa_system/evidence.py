"""Resolve a raw citation to one stable chunk; never guess ambiguous old labels."""

import re
from collections import defaultdict
from typing import Any

from src.knowledge_base.identity import unique_chunks

REF_PATTERN = re.compile(r"\[Ref\s+([^\]]+)\]")
STRICT_REF_PATTERN = re.compile(r"\[Ref\s+([^\]]+)\]|\[(\d+)\]")


def reference_pattern(allow_legacy: bool):
    return REF_PATTERN if allow_legacy else STRICT_REF_PATTERN


def citation_label(match) -> str:
    return (match.group(1) or match.group(2)).strip()


def citation_map(
    context: list[dict[str, Any]],
) -> tuple[list[dict], dict[str, list[str]]]:
    chunks = unique_chunks(context)
    aliases: dict[str, set[str]] = defaultdict(set)
    for doc in chunks:
        cid = doc["chunk_id"]
        for label in (cid, str(doc["chunk_index"]), *doc["sources"]):
            aliases[label].add(cid)
    return chunks, {label: sorted(ids) for label, ids in aliases.items()}


def resolve_citations(
    answer: str, context: list[dict], *, allow_legacy: bool = True
) -> dict:
    chunks, aliases = citation_map(context)
    legacy_aliases = aliases
    if not allow_legacy:
        aliases = {chunk["chunk_id"]: [chunk["chunk_id"]] for chunk in chunks}
    counts: dict[str, int] = defaultdict(int)
    unresolved = []
    for match in reference_pattern(allow_legacy).finditer(answer):
        label = citation_label(match)
        candidates = aliases.get(label, [])
        if len(candidates) == 1:
            counts[candidates[0]] += 1
        else:
            unresolved.append(
                {
                    "marker": match.group(0),
                    "reason": (
                        "noncanonical"
                        if not allow_legacy
                        and (match.group(1) is None or label in legacy_aliases)
                        else "ambiguous"
                        if candidates
                        else "unknown"
                    ),
                    "candidate_chunk_ids": candidates,
                }
            )
    return {
        "chunks": chunks,
        "aliases": aliases,
        "counts": dict(counts),
        "unresolved": unresolved,
    }
