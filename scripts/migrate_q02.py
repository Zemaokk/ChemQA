"""Replay PDF extraction to attach verifiable page/text locations to existing IDs.

Default is preview. --apply backs up both files and updates metadata only.
Records whose exact text cannot be replayed are explicitly marked unavailable.
"""

import argparse
import hashlib
import json
import os
from collections import Counter
from pathlib import Path

from config.settings import BASE_DIR, settings
from src.knowledge_base.identity import normalize_chunk, resolve_source
from src.knowledge_base.location import locate_chunks, unavailable_location
from src.knowledge_base.pdf_loader import PDFLoader


def _replay(doc: dict) -> tuple[list[dict], str | None]:
    for source in doc["sources"]:
        try:
            path = resolve_source(source)
        except ValueError:
            continue
        extracted = PDFLoader().load_pdf(str(path))
        if not extracted:
            continue
        document = extracted[0]
        if document["metadata"]["doc_id"] != doc["doc_id"]:
            continue
        return locate_chunks(
            document, settings.LEGACY_CHUNK_WORDS, settings.LEGACY_CHUNK_OVERLAP_WORDS
        ), None
    return [], "matching_pdf_not_available"


def migrate(processed: list[dict], index: dict) -> tuple[list[dict], dict, dict]:
    if len(processed) != len(index["documents"]) or len(processed) != len(
        index["vectors"]
    ):
        raise ValueError("Processed records and vector rows do not align")
    if any(d.get("text_processing_version") for d in index["documents"]):
        raise ValueError(
            "Q02 migration only replays legacy word chunks; Q03 data already has source locations"
        )
    replays = {}
    chunks, docs = [], []
    counts = Counter()
    reasons = Counter()
    for old_chunk, old_doc in zip(processed, index["documents"], strict=True):
        chunk, doc = normalize_chunk(old_chunk), normalize_chunk(old_doc)
        if chunk["chunk_id"] != doc["chunk_id"] or chunk["text"] != doc["text"]:
            raise ValueError("Processed record and index document differ")
        if doc["doc_id"] not in replays:
            replays[doc["doc_id"]] = _replay(doc)
        locations, reason = replays[doc["doc_id"]]
        position = doc["chunk_index"]
        if reason:
            location = unavailable_location(reason)
        elif position >= len(locations) or locations[position]["text"] != doc["text"]:
            location = unavailable_location(
                "chunk_text_differs_from_current_pdf_extraction"
            )
        else:
            location = {
                k: v
                for k, v in locations[position].items()
                if k not in ("text", "chunk_index")
            }
        for record in (chunk, doc):
            for field in (
                "location_version",
                "location_status",
                "location_reason",
                "location_extractor",
                "page_numbers",
                "source_spans",
            ):
                record.pop(field, None)
            record.update(location)
        chunks.append(
            {
                "text": chunk["text"],
                "metadata": {k: v for k, v in chunk.items() if k != "text"},
            }
        )
        docs.append(doc)
        counts[location["location_status"]] += 1
        if (
            location["location_status"] == "located"
            and len(location["page_numbers"]) > 1
        ):
            counts["cross_page"] += 1
        if location.get("location_reason"):
            reasons[location["location_reason"]] += 1
    report = {
        "rows": len(docs),
        "unique_pdf_contents": len(replays),
        **counts,
        "unavailable_reasons": dict(reasons),
        "text_ids_vectors_changed": False,
    }
    return chunks, {**index, "documents": docs}, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    chunk_path = Path(settings.PROCESSED_DIR) / "processed_chunks.json"
    index_path = Path(settings.VECTOR_DB_DIR) / "vector_index.json"
    originals = {p: p.read_bytes() for p in (chunk_path, index_path)}
    old_chunks, old_index = (
        json.loads(originals[chunk_path]),
        json.loads(originals[index_path]),
    )
    chunks, index, report = migrate(old_chunks, old_index)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not args.apply:
        print("Read-only preview; use --apply to back up and add location metadata.")
        return
    if chunks == old_chunks and index == old_index:
        print("Already migrated; no files changed.")
        return
    backup_dir = Path(BASE_DIR) / "output" / "q02_backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    for path, content in originals.items():
        digest = hashlib.sha256(content).hexdigest()
        backup = backup_dir / f"{path.stem}.{digest}.json"
        if backup.exists() and backup.read_bytes() != content:
            raise ValueError("Backup content mismatch")
        backup.write_bytes(content)
    for path, data in ((chunk_path, chunks), (index_path, index)):
        temporary = path.with_suffix(".q02.tmp")
        temporary.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        os.replace(temporary, path)
    print(f"Location metadata applied; originals backed up in {backup_dir}")


if __name__ == "__main__":
    main()
