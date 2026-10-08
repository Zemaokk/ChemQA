"""Compare fixed G candidates with/without a pinned local reranker; no generation."""

import argparse
import json
import resource
import statistics
import time
from pathlib import Path

import numpy as np

from config.settings import BASE_DIR, resolve_path
from scripts.validate_q065g import fingerprints as prior_fingerprints
from scripts.validate_q065g import load_inputs
from src.evaluation.metrics import aggregate_metrics, retrieval_metrics
from src.knowledge_base.reranked_search import RerankedSearch
from src.knowledge_base.reranker import QwenReranker
from src.knowledge_base.retriever import Retriever
from src.utils.artifacts import ArtifactRun, sha256_file, write_json

ROOT = Path(BASE_DIR)
PROFILE = ROOT / "config/q065h_reranker.json"


def read(path):
    return json.loads(Path(path).read_text())


def source():
    summary = read(ROOT / "docs/Q06_5G_FULL.json")
    directory = Path(summary["artifact_directory"])
    run = read(directory / "run.json")
    if run.get("kind") != "hybrid_runs" or run.get("status") != "ready":
        raise ValueError("G candidate is not ready")
    for name, checksum in run["files"].items():
        if sha256_file(directory / name) != checksum:
            raise ValueError("G artifact checksum mismatch")
    if run["dataset_manifest_sha256"] != sha256_file(
        ROOT / "evaluation/manifest.json"
    ) or run["protocol_sha256"] != sha256_file(ROOT / "config/q065g_experiment.json"):
        raise ValueError("Frozen G dataset/protocol changed")
    store, _, questions, _, _ = load_inputs()
    ranks = read(directory / "rankings.json")
    mode = read(directory / "retrieval_profile.json")["mode"]
    candidates = []
    for question, row in zip(questions, ranks["records"], strict=True):
        if question["split"] != "dev" or question["question_id"] != row["question_id"]:
            raise ValueError("Reserve or changed query order forbidden")
        hits = []
        for item in row["rankings"][mode]:
            doc = store.storage.documents[item["row_id"]]
            if doc["chunk_id"] != item["chunk_id"] or doc["doc_id"] != item["doc_id"]:
                raise ValueError("Frozen candidate row mapping mismatch")
            hits.append(
                {
                    "document": doc,
                    "score": item["score"],
                    "score_kind": item["score_kind"],
                }
            )
        if len(hits) != 50 or len({h["document"]["chunk_id"] for h in hits}) != 50:
            raise ValueError("Expected 50 unique frozen candidates")
        candidates.append(hits)
    return directory, store, questions, candidates, ranks, mode


def fingerprints():
    directory = Path(read(ROOT / "docs/Q06_5G_FULL.json")["artifact_directory"])
    return {
        **prior_fingerprints(),
        **{
            str((directory / name).relative_to(ROOT)): sha256_file(directory / name)
            for name in [
                "run.json",
                "rankings.json",
                "retrieval_profile.json",
                "benchmark.json",
            ]
        },
        "config/q065h_reranker.json": sha256_file(PROFILE),
    }


def select_enabled(summaries, median_seconds, profile):
    off, on = summaries["off"]["at_k"], summaries["on"]["at_k"]
    return (
        on["10"]["complete_anchor_recall"] > off["10"]["complete_anchor_recall"]
        and on["5"]["mean_anchor_character_coverage"]
        >= off["5"]["mean_anchor_character_coverage"]
        and on["10"]["annotated_doc_recall"] >= off["10"]["annotated_doc_recall"]
        and median_seconds <= profile["maximum_median_rerank_seconds"]
    )


def evaluate(questions, candidates, scores):
    if (
        len(questions) != len(candidates)
        or scores.shape != (len(questions), 50)
        or not np.isfinite(scores).all()
    ):
        raise ValueError("Reranker matrix/input rows mismatch")
    records = []
    groups = {"off": [], "on": []}
    for question, hits, values in zip(questions, candidates, scores, strict=True):
        if question["split"] != "dev":
            raise ValueError("Reserve queries forbidden")
        order = np.argsort(-values, kind="stable")
        ranked = [hits[int(i)] for i in order]
        metrics = {
            "off": retrieval_metrics(question, hits[:10]),
            "on": retrieval_metrics(question, ranked[:10]),
        }
        for mode, rows in groups.items():
            rows.append({"metrics": metrics[mode]})
        records.append(
            {
                "question_id": question["question_id"],
                "category": question["category"],
                "answerability": question["answerability"],
                "metrics": metrics,
                "original_candidate_ids": [h["document"]["chunk_id"] for h in hits],
                "reranked_candidate_ids": [h["document"]["chunk_id"] for h in ranked],
                "original_scores": [h["score"] for h in hits],
                "reranker_logit_differences": values.tolist(),
                "reranked_original_positions": (order + 1).tolist(),
            }
        )
    return {
        "records": records,
        "summaries": {
            mode: aggregate_metrics(rows, "metrics") for mode, rows in groups.items()
        },
    }


def run(device):
    before = fingerprints()
    directory, store, questions, candidates, g, mode = source()
    profile = read(PROFILE)
    try:
        start = time.perf_counter()
        reranker = QwenReranker(profile, device=device)
        load_seconds = time.perf_counter() - start
        # Validate every complete template before spending inference time.
        counts = []
        for q, hits in zip(questions, candidates, strict=True):
            query_counts = []
            for start in range(0, 50, profile["batch_size"]):
                _, n = reranker.prepare(
                    [
                        (q["question"], h["document"]["text"])
                        for h in hits[start : start + profile["batch_size"]]
                    ]
                )
                query_counts.extend(n)
            counts.append(query_counts)
        matrices = []
        timings = []
        for question, hits in zip(questions, candidates, strict=True):
            start = time.perf_counter()
            values, n = reranker.score(question["question"], hits)
            seconds = time.perf_counter() - start
            matrices.append(values)
            timings.append(seconds)
            print(f"{question['question_id']}: 50/50; {seconds:.2f}s", flush=True)
        scores = np.stack(matrices)
        evaluation = evaluate(questions, candidates, scores)
        if evaluation["summaries"]["off"] != g["summary_top10"][mode]:
            raise ValueError("G baseline metrics changed")
        enabled = select_enabled(
            evaluation["summaries"], statistics.median(timings), profile
        )
        with ArtifactRun("rerank_runs") as artifact:
            np.save(artifact.path / "scores.npy", scores, allow_pickle=False)
            write_json(artifact.path / "rankings.json", evaluation)
            write_json(artifact.path / "model_profile.json", reranker.manifest())
            runtime_profile = {
                "schema": "chemqa-reranked-search-v1",
                "enabled": enabled,
                "retrieval_profile": str(directory / "retrieval_profile.json"),
                "retrieval_run_sha256": sha256_file(directory / "run.json"),
                "model_profile": reranker.manifest(),
                "score_policy": "raw_only_no_context_threshold",
                "candidate_window": 50,
            }
            write_json(artifact.path / "reranker_profile.json", runtime_profile)
            target = artifact.publish(
                "ready",
                {
                    "files": {
                        name: sha256_file(artifact.path / name)
                        for name in [
                            "scores.npy",
                            "rankings.json",
                            "model_profile.json",
                            "reranker_profile.json",
                        ]
                    },
                    "source_G_directory": str(directory),
                    "source_G_run_sha256": sha256_file(directory / "run.json"),
                    "dataset_manifest_sha256": sha256_file(
                        ROOT / "evaluation/manifest.json"
                    ),
                    "profile_sha256": sha256_file(PROFILE),
                },
            )
        if before != fingerprints():
            raise ValueError("Immutable inputs changed")
        report = {
            "schema": "chemqa-q065h-evaluation-v1",
            "status": "passed",
            "artifact_directory": str(target),
            "source_G_directory": str(directory),
            "model_profile": reranker.manifest(),
            "actual_device": str(reranker.model.device),
            "actual_parameter_dtype": str(next(reranker.model.parameters()).dtype),
            "model_load_seconds": load_seconds,
            "query_count": 20,
            "pairs": 1000,
            "candidate_window": 50,
            "candidate_sets_and_texts_unchanged": True,
            "full_template_tokens": {
                "minimum": min(map(min, counts)),
                "maximum": max(map(max, counts)),
                "total": sum(map(sum, counts)),
                "per_query": counts,
            },
            "actual_preprocessing_ids_match_untruncated_template": True,
            "over_limit_inputs": 0,
            "summaries": evaluation["summaries"],
            "reranker_enabled_in_candidate_workflow": enabled,
            "incremental_rerank_seconds": {
                "per_query": timings,
                "median": statistics.median(timings),
                "p95": float(np.percentile(timings, 95)),
                "total": sum(timings),
            },
            "rss_high_water_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            "input_fingerprints_before": before,
            "input_fingerprints_after": fingerprints(),
            "annotation_quality": "AI draft; domain review pending",
            "production_default_switched": False,
            "reserve_queries_executed": 0,
            "generation_requests": 0,
            "embedding_query_reencoding_count": 0,
        }
        write_json(ROOT / "docs/Q06_5H_FULL.json", report)
        changes = []
        for row in evaluation["records"]:
            if row["answerability"] != "answerable":
                continue
            off = row["metrics"]["off"]["at_k"]["10"]
            on = row["metrics"]["on"]["at_k"]["10"]
            changes.append(
                {
                    "question_id": row["question_id"],
                    "category": row["category"],
                    "off_complete_anchor_recall_at_10": off["complete_anchor_recall"],
                    "on_complete_anchor_recall_at_10": on["complete_anchor_recall"],
                    "difference": on["complete_anchor_recall"]
                    - off["complete_anchor_recall"],
                    "selected_anchor_coverage": (on if enabled else off)[
                        "anchor_coverage"
                    ],
                }
            )
        write_json(
            ROOT / "docs/Q06_5H_FAILURES.json",
            {
                "selected_reranker_enabled": enabled,
                "annotation_quality": report["annotation_quality"],
                "improved": [r for r in changes if r["difference"] > 0],
                "regressed": [r for r in changes if r["difference"] < 0],
                "selected_incomplete": [
                    r
                    for r in changes
                    if any(v < 1 for v in r["selected_anchor_coverage"].values())
                ],
                "all_comparisons": changes,
            },
        )
        print(
            json.dumps(
                {
                    "status": "passed",
                    "artifact_directory": str(target),
                    "reranker_enabled": enabled,
                }
            )
        )
    finally:
        store.storage.close()


def replay(directory):
    before = fingerprints()
    manifest = read(directory / "run.json")
    if (
        manifest.get("status") != "ready"
        or manifest.get("kind") != "rerank_runs"
        or manifest["profile_sha256"] != sha256_file(PROFILE)
        or manifest["dataset_manifest_sha256"]
        != sha256_file(ROOT / "evaluation/manifest.json")
    ):
        raise ValueError("Rerank artifact/profile/dataset mismatch")
    for name, checksum in manifest["files"].items():
        if sha256_file(directory / name) != checksum:
            raise ValueError("Rerank artifact checksum mismatch")
    gdir, store, questions, candidates, _, _ = source()
    try:
        if manifest["source_G_run_sha256"] != sha256_file(gdir / "run.json"):
            raise ValueError("Source G run changed")
        actual = evaluate(
            questions, candidates, np.load(directory / "scores.npy", allow_pickle=False)
        )
        if actual != read(directory / "rankings.json") or before != fingerprints():
            raise ValueError("Frozen-score replay changed rankings or metrics")
        write_json(
            ROOT / "docs/Q06_5H_REPLAY.json",
            {
                "status": "passed",
                "artifact_directory": str(directory),
                "all_scores_rankings_metrics_equal": True,
                "candidate_ids_and_order_preserved": True,
                "immutable_inputs_unchanged": True,
                "model_inference_repeated": False,
                "reserve_queries_executed": 0,
                "generation_requests": 0,
            },
        )
    finally:
        store.storage.close()


def runtime(directory, device):
    """Repeat D01 locally through the public raw retrieval entry point."""
    before = fingerprints()
    _, store, questions, candidates, _, _ = source()
    try:
        engine = RerankedSearch.from_profile(
            store, directory / "reranker_profile.json", device=device
        )
        retriever = Retriever.__new__(Retriever)
        retriever.vector_store = store
        retriever.raw_search = engine
        results = retriever.search(questions[0]["question"], 10)
        saved = read(directory / "rankings.json")["records"][0]
        enabled = engine.reranker is not None
        expected = saved[
            "reranked_candidate_ids" if enabled else "original_candidate_ids"
        ][:10]
        if [h["document"]["chunk_id"] for h in results] != expected:
            raise ValueError("Public selected-profile retrieval changed D01 ranking")
        if enabled:
            actual = {h["document"]["chunk_id"]: h["score"] for h in results}
            original = dict(
                zip(
                    saved["original_candidate_ids"],
                    saved["reranker_logit_differences"],
                    strict=True,
                )
            )
            difference = max(
                abs(score - original[cid]) for cid, score in actual.items()
            )
            if difference > 0.001:
                raise ValueError("Real model replay logits drifted")
        else:
            difference = None
        try:
            retriever.retrieve_relevant_context(questions[0]["question"], min_score=0)
        except ValueError as error:
            if "raw-search only" not in str(error):
                raise
        else:
            raise ValueError("Uncalibrated reranker logits entered context filtering")
        if before != fingerprints():
            raise ValueError("Runtime changed frozen inputs")
        write_json(
            ROOT / "docs/Q06_5H_RUNTIME.json",
            {
                "status": "passed",
                "artifact_directory": str(directory),
                "question_id": questions[0]["question_id"],
                "candidate_profile_enabled": enabled,
                "public_retriever_top10_equal": True,
                "repeated_real_model_top10_max_logit_difference": difference,
                "context_threshold_blocked": True,
                "source_candidate_window": len(candidates[0]),
                "immutable_inputs_unchanged": True,
                "frozen_query_embeddings_used": True,
                "generation_requests": 0,
                "reserve_queries_executed": 0,
            },
        )
    finally:
        store.storage.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["run", "replay", "runtime"])
    parser.add_argument("--device", choices=["auto", "cpu", "mps"], default="auto")
    parser.add_argument("--candidate", type=Path)
    args = parser.parse_args()
    if args.mode == "run":
        run(args.device)
    elif args.candidate:
        action = replay if args.mode == "replay" else runtime
        if args.mode == "replay":
            action(resolve_path(args.candidate))
        else:
            action(resolve_path(args.candidate), args.device)
    else:
        parser.error("replay/runtime requires --candidate")


if __name__ == "__main__":
    main()
