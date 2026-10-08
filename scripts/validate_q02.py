"""Independently re-open PDFs to verify stored page intervals and raw excerpts."""

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

import pymupdf

from config.settings import settings
from src.knowledge_base.identity import document_id, normalize_chunk, resolve_source
from src.knowledge_base.text_processor import TextProcessor


def validate(index: dict, processed: list[dict], baseline: dict | None = None) -> dict:
    docs = index["documents"]
    if len(docs) != len(index["vectors"]) or len(docs) != len(processed):
        raise ValueError("Rows do not align")
    if baseline is not None:
        if index["vectors"] != baseline["vectors"] or len(docs) != len(
            baseline["documents"]
        ):
            raise ValueError("Migration changed vector values or row count")
        fields = ("text", "doc_id", "chunk_id", "chunk_index")
        if any(
            any(doc[k] != old[k] for k in fields)
            for doc, old in zip(docs, baseline["documents"], strict=True)
        ):
            raise ValueError("Migration changed chunk text or identity")
    pages_by_doc = {}
    counts, unmatched = Counter(), Counter()
    processor = TextProcessor(legacy=True)
    current_processor = TextProcessor()
    for record, processed_record in zip(docs, processed, strict=True):
        doc, chunk = normalize_chunk(record), normalize_chunk(processed_record)
        if (
            doc["chunk_id"] != chunk["chunk_id"]
            or doc["source_spans"] != chunk["source_spans"]
        ):
            raise ValueError("Processed and index location records differ")
        status = doc["location_status"]
        counts[status] += 1
        if status == "unavailable":
            unmatched[doc["source"]] += 1
            continue
        if doc["doc_id"] not in pages_by_doc:
            path = resolve_source(doc["source"])
            pdf_bytes = path.read_bytes()
            if document_id(pdf_bytes) != doc["doc_id"]:
                raise ValueError("PDF bytes no longer match the chunk's document")
            with pymupdf.open(stream=pdf_bytes, filetype="pdf") as pdf:
                pages_by_doc[doc["doc_id"]] = [
                    page.get_text("text", sort=False) for page in pdf
                ]
        pages = pages_by_doc[doc["doc_id"]]
        for span in doc["source_spans"]:
            if span["page_number"] > len(pages):
                raise ValueError(
                    "Stored page number exceeds the current PDF page count"
                )
            raw = pages[span["page_number"] - 1]
            if (
                span["char_end"] > len(raw)
                or raw[span["char_start"] : span["char_end"]] != span["raw_text"]
            ):
                raise ValueError(
                    "Stored raw excerpt differs from its PDF page interval"
                )
            counts["verified_spans"] += 1
        raw_excerpt = "".join(span["raw_text"] for span in doc["source_spans"])
        cleaner = current_processor if doc.get("text_processing_version") else processor
        if " ".join(cleaner.clean_text(raw_excerpt).split()) != doc["text"]:
            raise ValueError("Raw excerpt does not reconstruct the stored chunk text")
        if len(doc["page_numbers"]) > 1:
            counts["cross_page"] += 1
    return {
        "rows": len(docs),
        **counts,
        "verified_pdf_contents": len(pages_by_doc),
        "unavailable_by_source": dict(unmatched),
        "text_ids_vectors_preserved_against_baseline": True
        if baseline is not None
        else None,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-index", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    index_path = Path(settings.VECTOR_DB_DIR) / "vector_index.json"
    chunks_path = Path(settings.PROCESSED_DIR) / "processed_chunks.json"
    baseline = (
        json.loads(args.baseline_index.read_text()) if args.baseline_index else None
    )
    report = validate(
        json.loads(index_path.read_text()),
        json.loads(chunks_path.read_text()),
        baseline,
    )
    report["index_sha256"] = hashlib.sha256(index_path.read_bytes()).hexdigest()
    report["chunks_sha256"] = hashlib.sha256(chunks_path.read_bytes()).hexdigest()
    if args.baseline_index:
        report["baseline_index_sha256"] = hashlib.sha256(
            args.baseline_index.read_bytes()
        ).hexdigest()
    serialized = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    print(serialized)
    if args.report:
        args.report.write_text(serialized, encoding="utf-8")


if __name__ == "__main__":
    main()
