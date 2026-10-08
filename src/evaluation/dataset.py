"""Validate frozen question files and exact source anchors, without ranking reserve queries."""

import json
from collections import Counter
from pathlib import Path

import pymupdf

from config.settings import BASE_DIR
from src.knowledge_base.identity import document_id, resolve_source
from src.utils.artifacts import sha256_file

DATASET_DIR = Path(BASE_DIR) / "evaluation"
CATEGORIES = {
    "single_fact",
    "conditions",
    "mechanism",
    "numeric",
    "system_boundary",
    "comparison",
    "insufficient_evidence",
}


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def validate_dataset(directory=DATASET_DIR, *, verify_sources=True):
    directory = Path(directory)
    manifest = read_json(directory / "manifest.json")
    if manifest.get("schema") != "chemqa-eval-manifest-v1":
        raise ValueError("Unsupported evaluation manifest")
    for name in ("dev.json", "reserve.json", "documents.json", "RUBRIC.md"):
        if manifest["files_sha256"].get(name) != sha256_file(directory / name):
            raise ValueError(f"Frozen dataset checksum mismatch: {name}")
    catalog = read_json(directory / "documents.json")
    if catalog.get("schema") != "chemqa-eval-documents-v1":
        raise ValueError("Unsupported document catalog")
    documents = catalog["documents"]
    questions, articles, seen = {}, {}, set()
    pages, pdf_ids = {}, {}
    for split in ("dev", "reserve"):
        data = read_json(directory / f"{split}.json")
        if (
            data.get("schema") != "chemqa-eval-questions-v1"
            or data.get("split") != split
            or data.get("version") != manifest["version"]
        ):
            raise ValueError("Question schema, split or version mismatch")
        questions[split] = data["questions"]
        articles[split] = set()
        if len(questions[split]) != manifest["split_counts"][split]:
            raise ValueError("Split count differs from manifest")
        for row in questions[split]:
            qid = row["question_id"]
            if (
                qid in seen
                or row["split"] != split
                or not isinstance(row["question"], str)
                or not row["question"].strip()
            ):
                raise ValueError("Invalid or duplicate question identity")
            seen.add(qid)
            if row["category"] not in CATEGORIES or row["answerability"] not in {
                "answerable",
                "scoped_insufficient",
            }:
                raise ValueError("Unknown question category or answerability")
            if row["answerability"] == "scoped_insufficient" and not row.get(
                "evidence_scope"
            ):
                raise ValueError("Insufficiency must have an explicit bounded scope")
            annotation = row["annotation"]
            if annotation["review_status"] not in {"pending", "approved", "disputed"}:
                raise ValueError("Unknown domain review state")
            if annotation["review_status"] == "approved" and not annotation.get(
                "human_reviewer"
            ):
                raise ValueError(
                    "Domain approval requires an identified human reviewer"
                )
            if (
                not row["evidence"]
                or not row["answer_points"]
                or not row["must_not_claim"]
            ):
                raise ValueError(
                    "Questions need evidence, answer points and boundary notes"
                )
            evidence_ids = set()
            for anchor in row["evidence"]:
                key = anchor["document_key"]
                doc = documents[key]
                if (
                    anchor["evidence_id"] in evidence_ids
                    or anchor["doc_id"] != doc["doc_id"]
                ):
                    raise ValueError(
                        "Duplicate evidence identity or mismatched PDF identity"
                    )
                evidence_ids.add(anchor["evidence_id"])
                articles[split].add(doc["article_id"])
                page, start, end = (
                    anchor["page_number"],
                    anchor["char_start"],
                    anchor["char_end"],
                )
                if (
                    any(type(value) is not int for value in (page, start, end))
                    or not 1 <= page <= doc["pdf_pages"]
                    or not 0 <= start < end
                    or not anchor["quote"]
                    or len(anchor["quote"]) != end - start
                ):
                    raise ValueError("Invalid evidence interval")
                if verify_sources:
                    if key not in pages:
                        source = resolve_source(doc["source"])
                        pdf_ids[key] = document_id(source.read_bytes())
                        with pymupdf.open(source) as pdf:
                            pages[key] = [p.get_text("text", sort=False) for p in pdf]
                        if (
                            pdf_ids[key] != doc["doc_id"]
                            or len(pages[key]) != doc["pdf_pages"]
                        ):
                            raise ValueError("Source PDF changed")
                    if pages[key][page - 1][start:end] != anchor["quote"]:
                        raise ValueError(
                            "Evidence quote differs from exact PDF interval"
                        )
            point_ids = set()
            for point in row["answer_points"]:
                if (
                    not point["text"]
                    or point["point_id"] in point_ids
                    or not point["evidence_ids"]
                    or not set(point["evidence_ids"]) <= evidence_ids
                ):
                    raise ValueError("Answer point refers to missing evidence")
                point_ids.add(point["point_id"])
    if articles["dev"] & articles["reserve"]:
        raise ValueError("Development and reserve article groups overlap")
    report = {
        "status": "passed",
        "version": manifest["version"],
        "split_counts": {split: len(rows) for split, rows in questions.items()},
        "source_pdfs_verified": len(pages),
        "exact_evidence_intervals": sum(
            len(row["evidence"]) for rows in questions.values() for row in rows
        ),
        "article_groups": {split: len(ids) for split, ids in articles.items()},
        "article_group_overlap": 0,
        "domain_review_states": dict(
            Counter(
                row["annotation"]["review_status"]
                for rows in questions.values()
                for row in rows
            )
        ),
        "source_verification_enabled": verify_sources,
        "reserve_ranked_or_generated": False,
    }
    return manifest, documents, questions, report
