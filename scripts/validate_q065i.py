"""Offline evidence-selection preview/replay on the frozen H dev candidates."""

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from config.prompts import ORGANIC_ELECTROCATALYSIS_PROMPT
from scripts.validate_q065h import fingerprints as prior_fingerprints
from scripts.validate_q065h import read, source
from src.api_integration.api_handler import DeepSeekAPIHandler
from src.evaluation.metrics import aggregate_metrics, retrieval_metrics
from src.qa_system.context_selection import select_context, span_overlap, verify_budget
from src.qa_system.response_formatter import ResponseFormatter
from src.utils.artifacts import ArtifactRun, sha256_file, write_json

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "config/q065i_context.json"


def fingerprints():
    h = Path(read(ROOT / "docs/Q06_5H_FULL.json")["artifact_directory"])
    return {
        **prior_fingerprints(),
        **{
            str((h / name).relative_to(ROOT)): sha256_file(h / name)
            for name in [
                "run.json",
                "rankings.json",
                "reranker_profile.json",
                "model_profile.json",
                "scores.npy",
            ]
        },
        "config/q065i_context.json": sha256_file(POLICY),
    }


def duplicate_fraction(chunks):
    total = sum(len(c["text"]) for c in chunks)
    # Located source-character overlap; ratio to located source characters only.
    located = [c for c in chunks if c.get("location_status") == "located"]
    lengths = [
        sum(s["char_end"] - s["char_start"] for s in c["source_spans"]) for c in located
    ]
    repeated = sum(
        span_overlap(c, located[:i]) * lengths[i] for i, c in enumerate(located)
    )
    return {
        "source_character_overlap_fraction": repeated / sum(lengths)
        if sum(lengths)
        else None,
        "text_characters": total,
        "located_chunks": len(located),
        "exact_normalized_text_duplicate_count": len(chunks)
        - len({" ".join(c["text"].split()) for c in chunks}),
    }


def evaluate(body):
    hdir = Path(read(ROOT / "docs/Q06_5H_FULL.json")["artifact_directory"])
    run = read(hdir / "run.json")
    if (
        run.get("kind") != "rerank_runs"
        or run.get("status") != "ready"
        or run["dataset_manifest_sha256"]
        != sha256_file(ROOT / "evaluation/manifest.json")
    ):
        raise ValueError("H source is not ready")
    for name, checksum in run["files"].items():
        if sha256_file(hdir / name) != checksum:
            raise ValueError("Frozen H checksum changed")
    gdir, store, questions, candidates, _, _ = source()
    try:
        if run["source_G_run_sha256"] != sha256_file(gdir / "run.json"):
            raise ValueError("H/G binding changed")
        selected_h = read(hdir / "reranker_profile.json")["enabled"]
        rows = read(hdir / "rankings.json")["records"]
        policy = read(POLICY)
        snapshots, records = [], []
        groups = {"h_top10": [], "selected": []}
        for question, hits, row in zip(questions, candidates, rows, strict=True):
            if (
                question["split"] != "dev"
                or question["question_id"] != row["question_id"]
            ):
                raise ValueError("Reserve or query order change forbidden")
            by_id = {h["document"]["chunk_id"]: h for h in hits}
            ids = row[
                "reranked_candidate_ids" if selected_h else "original_candidate_ids"
            ]
            if len(ids) != 50 or set(ids) != set(by_id):
                raise ValueError("Frozen H candidate identities changed")
            ordered = [by_id[cid] for cid in ids]
            result = select_context(question["question"], ordered, policy, body)
            chunks = result.prepared.chunks
            verify_budget(result.prepared, body)
            # Exercise canonical-ID citation mapping on exactly the frozen selection.
            answer = "\n".join("[Ref " + c["chunk_id"] + "]" for c in chunks)
            mapping = ResponseFormatter().format_answer(
                answer, chunks, allow_legacy=False
            )
            if mapping["unresolved_citations"] or {
                e["chunk_id"] for e in mapping["evidence_map"]
            } != {c["chunk_id"] for c in chunks}:
                raise ValueError("Citation identity mapping drifted")
            metrics = {
                "h_top10": retrieval_metrics(question, ordered[:10]),
                "selected": retrieval_metrics(
                    question, [{"document": c} for c in chunks]
                ),
            }
            for mode, items in groups.items():
                items.append({"metrics": metrics[mode]})
            snapshots.append(
                {
                    "question_id": question["question_id"],
                    "question": question["question"],
                    "prepared": result.prepared.record(),
                    "evidence": chunks,
                    "selection": result.audit,
                }
            )
            records.append(
                {
                    "question_id": question["question_id"],
                    "answerability": question["answerability"],
                    "selected_ids": [c["chunk_id"] for c in chunks],
                    "selected_ranks": [
                        r["rank"] for r in result.audit["records"] if r["selected"]
                    ],
                    "selected_count": len(chunks),
                    "selected_document_count": len({c["doc_id"] for c in chunks}),
                    "h_top10_document_count": len(
                        {h["document"]["doc_id"] for h in ordered[:10]}
                    ),
                    "input_estimate": result.prepared.budget["input_estimate"],
                    "total_estimate": result.prepared.budget["total_estimate"],
                    "exclusion_reasons": dict(
                        Counter(
                            r["reason"]
                            for r in result.audit["records"]
                            if not r["selected"]
                        )
                    ),
                    "duplicates": {
                        "h_top10": duplicate_fraction(
                            [h["document"] for h in ordered[:10]]
                        ),
                        "selected": duplicate_fraction(chunks),
                    },
                    "metrics": metrics,
                }
            )
        return {
            "schema": "chemqa-context-preview-v1",
            "source_H_directory": str(hdir),
            "source_H_run_sha256": sha256_file(hdir / "run.json"),
            "policy": policy,
            "request_body": body,
            "records": records,
            "summaries": {
                mode: aggregate_metrics(items, "metrics")
                for mode, items in groups.items()
            },
            "annotation_quality": "AI draft; domain review pending",
            "provider_exact_input_tokens": None,
            "generation_requests": 0,
            "reserve_queries_executed": 0,
        }, snapshots
    finally:
        store.storage.close()


def validate(mode, directory=None):
    before = fingerprints()
    if mode == "run":
        body = DeepSeekAPIHandler().request_parameters()["body"]
        result, snapshots = evaluate(body)
        with ArtifactRun("context_runs") as artifact:
            write_json(artifact.path / "preview.json", result)
            write_json(artifact.path / "requests.json", snapshots)
            target = artifact.publish(
                "ready",
                {
                    "files": {
                        n: sha256_file(artifact.path / n)
                        for n in ["preview.json", "requests.json"]
                    },
                    "source_H_run_sha256": result["source_H_run_sha256"],
                    "policy_sha256": sha256_file(POLICY),
                    "prompt_template_sha256": hashlib.sha256(
                        ORGANIC_ELECTROCATALYSIS_PROMPT.encode()
                    ).hexdigest(),
                    "dataset_manifest_sha256": sha256_file(
                        ROOT / "evaluation/manifest.json"
                    ),
                },
            )
        report = {
            **result,
            "status": "passed",
            "artifact_directory": str(target),
            "input_fingerprints_before": before,
            "input_fingerprints_after": fingerprints(),
            "production_default_switched": False,
            "adoption_status": "experimental_policy_pending_Q10B",
            "exact_provider_token_budget_verified": False,
            "local_admission_budget_verified": True,
        }
        write_json(ROOT / "docs/Q06_5I_FULL.json", report)
        # Only local snapshots are generated; no transmission authorization inferred.
        print(
            json.dumps(
                {
                    "status": "passed",
                    "artifact_directory": str(target),
                    "generation_requests": 0,
                }
            )
        )
    else:
        run = read(directory / "run.json")
        if (
            run.get("kind") != "context_runs"
            or run.get("status") != "ready"
            or run["policy_sha256"] != sha256_file(POLICY)
            or run["dataset_manifest_sha256"]
            != sha256_file(ROOT / "evaluation/manifest.json")
        ):
            raise ValueError("Context artifact/policy/dataset changed")
        for name, checksum in run["files"].items():
            if sha256_file(directory / name) != checksum:
                raise ValueError("Context artifact checksum changed")
        saved = read(directory / "preview.json")
        actual, snapshots = evaluate(saved["request_body"])
        if (
            actual != saved
            or snapshots != read(directory / "requests.json")
            or run["source_H_run_sha256"] != actual["source_H_run_sha256"]
        ):
            raise ValueError("Replay changed selected evidence, requests or metrics")
        write_json(
            ROOT / "docs/Q06_5I_REPLAY.json",
            {
                "status": "passed",
                "artifact_directory": str(directory),
                "requests_selections_metrics_exact": True,
                "generation_requests": 0,
                "reserve_queries_executed": 0,
            },
        )
    if before != fingerprints():
        raise ValueError("Frozen H/G/F/E and legacy inputs changed")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("mode", choices=["run", "replay"])
    p.add_argument("--candidate", type=Path)
    args = p.parse_args()
    if args.mode == "replay" and args.candidate is None:
        p.error("replay needs --candidate")
    validate(args.mode, args.candidate)


if __name__ == "__main__":
    main()
