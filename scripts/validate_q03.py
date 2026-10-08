"""Audit source coverage, scientific text preservation and actual encoder inputs."""

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
import pymupdf

from config.settings import settings
from scripts.validate_q02 import validate as validate_locations
from src.knowledge_base.identity import resolve_source
from src.knowledge_base.text_processor import PROCESSING_VERSION
from src.knowledge_base.token_budget import TokenBudget


def validate(index: dict, processed: list[dict], model) -> dict:
    report = validate_locations(index, processed)
    budget = TokenBudget(model)
    if index.get("embedding") != budget.manifest():
        raise ValueError("Embedding manifest does not match the actual encoder")
    docs = index["documents"]
    vectors = np.asarray(index["vectors"])
    if (
        vectors.shape != (len(docs), model.get_sentence_embedding_dimension())
        or not np.isfinite(vectors).all()
    ):
        raise ValueError("Invalid embedding matrix")
    groups = defaultdict(list)
    counts = []
    for doc, processed_doc in zip(docs, processed, strict=True):
        if doc != {"text": processed_doc["text"], **processed_doc["metadata"]}:
            raise ValueError("Processed and index metadata differ")
        count = budget.count(doc["text"])
        if (
            doc.get("text_processing_version") != PROCESSING_VERSION
            or doc.get("word_count") != len(doc["text"].split())
            or doc.get("embedding_token_count") != count
            or doc.get("embedding_token_limit") != budget.limit
            or "num_tokens" in doc
            or count > budget.limit
            or doc["location_status"] != "located"
        ):
            raise ValueError("Invalid Q03 chunk counts/version/location")
        counts.append(count)
        groups[doc["doc_id"]].append(doc)
    # Compare untruncated IDs with the actual SentenceTransformer preprocessing path.
    for start in range(0, len(docs), 64):
        texts = [d["text"] for d in docs[start : start + 64]]
        actual = model.tokenize(texts)
        expected = budget.tokenizer(
            texts, truncation=False, padding=False, verbose=False
        )["input_ids"]
        for ids, mask, full in zip(
            actual["input_ids"].tolist(),
            actual["attention_mask"].tolist(),
            expected,
            strict=True,
        ):
            if [token for token, used in zip(ids, mask, strict=True) if used] != full:
                raise ValueError(
                    "Encoder truncates or changes the tokenizer's input IDs"
                )
    characters = 0
    for records in groups.values():
        with pymupdf.open(resolve_source(records[0]["source"])) as pdf:
            pages = [page.get_text("text", sort=False) for page in pdf]
        prefixes = [0]
        for page in pages:
            prefixes.append(prefixes[-1] + len(page))
        ranges = sorted(
            (
                prefixes[s["page_number"] - 1] + s["char_start"],
                prefixes[s["page_number"] - 1] + s["char_end"],
            )
            for doc in records
            for s in doc["source_spans"]
        )
        raw = "".join(pages)
        cursor = 0
        for first, last in ranges:
            if first > cursor and raw[cursor:first].strip():
                raise ValueError("Chunking dropped non-whitespace PDF characters")
            cursor = max(cursor, last)
        if raw[cursor:].strip():
            raise ValueError("Chunking dropped the end of a PDF")
        characters += sum(not char.isspace() for char in raw)
    report.update(
        {
            "embedding": budget.manifest(),
            "max_embedding_token_count": max(counts),
            "embedding_token_percentiles": np.percentile(
                counts, [0, 50, 90, 100]
            ).tolist(),
            "over_limit_chunks": 0,
            "actual_encoder_token_ids_match_untruncated_inputs": True,
            "source_nonwhitespace_characters_covered": characters,
            "pdf_contents_fully_covered": len(groups),
        }
    )
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--baseline-index", type=Path)
    args = parser.parse_args()
    from src.knowledge_base.vector_store import VectorStore

    store = VectorStore()
    index_path = Path(settings.VECTOR_DB_DIR) / "vector_index.json"
    chunks_path = Path(settings.PROCESSED_DIR) / "processed_chunks.json"
    report = validate(
        json.loads(index_path.read_text()),
        json.loads(chunks_path.read_text()),
        store.model,
    )
    report.update(
        {
            "index_sha256": hashlib.sha256(index_path.read_bytes()).hexdigest(),
            "chunks_sha256": hashlib.sha256(chunks_path.read_bytes()).hexdigest(),
        }
    )
    if args.baseline_index:
        baseline_bytes = args.baseline_index.read_bytes()
        baseline = json.loads(baseline_bytes)
        old_docs = baseline["documents"]
        new_docs = store.vector_index["documents"]
        if {d["doc_id"] for d in old_docs} != {d["doc_id"] for d in new_docs}:
            raise ValueError("Rebuild changed the set of PDF document identities")
        old_counts = [store.budget.count(d["text"]) for d in old_docs]
        report["baseline"] = {
            "index_sha256": hashlib.sha256(baseline_bytes).hexdigest(),
            "rows": len(old_docs),
            "over_limit_chunks": sum(n > store.budget.limit for n in old_counts),
            "token_percentiles": np.percentile(old_counts, [0, 50, 90, 100]).tolist(),
            "total_embedding_tokens": sum(old_counts),
            "pdf_document_ids_preserved": True,
        }
    serialized = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    print(serialized)
    if args.report:
        args.report.write_text(serialized, encoding="utf-8")


if __name__ == "__main__":
    main()
