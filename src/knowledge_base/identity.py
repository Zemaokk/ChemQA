"""Content-based PDF/chunk identities shared by ingestion and citation mapping."""

import hashlib
import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from config.settings import settings
from src.knowledge_base.location import validate_location

IDENTITY_VERSION = "sha256-pdf-chunk-v1"


def document_id(pdf_bytes: bytes) -> str:
    return "doc_" + hashlib.sha256(pdf_bytes).hexdigest()


def chunk_id(doc_id: str, index: int, text: str) -> str:
    if not re.fullmatch(r"doc_[0-9a-f]{64}", doc_id):
        raise ValueError("Invalid doc_id")
    if type(index) is not int or index < 0 or not isinstance(text, str) or not text:
        raise ValueError(
            "A chunk requires nonempty text and a nonnegative integer index"
        )
    payload = json.dumps([IDENTITY_VERSION, doc_id, index, text], ensure_ascii=False)
    return "chunk_" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def resolve_source(source: str) -> Path:
    """Resolve historical absolute paths by a unique basename in the current corpus."""
    path = Path(source)
    if path.is_file():
        return path.resolve()
    matches = list(Path(settings.RAW_PAPERS_DIR).rglob(path.name))
    if len(matches) != 1:
        raise ValueError(f"Cannot uniquely resolve PDF source: {source}")
    return matches[0].resolve()


@lru_cache(maxsize=512)
def _file_id(path: str, size: int, modified_ns: int) -> str:
    return document_id(Path(path).read_bytes())


def document_id_for_source(source: str) -> str:
    path = resolve_source(source)
    stat = path.stat()
    return _file_id(str(path), stat.st_size, stat.st_mtime_ns)


def normalize_chunk(record: dict[str, Any]) -> dict[str, Any]:
    """Flatten either chunk representation, validating any supplied stable IDs."""
    metadata = record.get("metadata", {})
    flat = dict(metadata)
    flat.update({k: v for k, v in record.items() if k != "metadata"})
    for field in ("doc_id", "chunk_id"):
        if field in record and field in metadata and record[field] != metadata[field]:
            raise ValueError(f"Conflicting {field} in chunk metadata")
    if flat.get("identity_version", IDENTITY_VERSION) != IDENTITY_VERSION:
        raise ValueError("Unsupported chunk identity version")
    source = flat.get("source")
    if not isinstance(source, str) or not source:
        raise ValueError("Chunk requires a source")
    doc_id = flat.get("doc_id") or document_id_for_source(source)
    expected = chunk_id(doc_id, flat.get("chunk_index"), flat.get("text"))
    if flat.get("chunk_id", expected) != expected:
        raise ValueError("chunk_id does not match its document, position and text")
    validate_location(flat)
    flat.update(doc_id=doc_id, chunk_id=expected, identity_version=IDENTITY_VERSION)
    flat["sources"] = sorted(set(flat.get("sources", []) + [source]))
    return flat


def merge_chunk_metadata(existing: dict, incoming: dict) -> None:
    """Merge source aliases and a verified location without discarding known positions."""
    if existing["chunk_id"] != incoming["chunk_id"]:
        raise ValueError("Cannot merge different chunks")
    if (
        existing.get("location_status") == incoming.get("location_status") == "located"
        and existing["source_spans"] != incoming["source_spans"]
    ):
        raise ValueError("Conflicting verified locations for the same chunk")
    existing["sources"] = sorted(set(existing["sources"] + incoming["sources"]))
    if (
        incoming.get("location_status") == "located"
        and existing.get("location_status") != "located"
    ):
        existing.pop("location_reason", None)
        for field in (
            "location_version",
            "location_status",
            "location_extractor",
            "page_numbers",
            "source_spans",
        ):
            existing[field] = incoming[field]
        validate_location(existing)


def unique_chunks(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    for record in records:
        doc = normalize_chunk(record)
        if doc["chunk_id"] in by_id:
            existing = by_id[doc["chunk_id"]]
            merge_chunk_metadata(existing, doc)
        else:
            by_id[doc["chunk_id"]] = doc
    return list(by_id.values())
