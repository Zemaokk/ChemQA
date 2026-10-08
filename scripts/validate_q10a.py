"""Validate source anchors and run/replay only the development retrieval baseline."""

import argparse
import os
import time
from pathlib import Path

import numpy as np

from config.prompts import PROMPT_VERSION
from config.settings import configure_paths, resolve_path, settings
from src.api_integration.prompt_builder import prepare_prompt
from src.evaluation.dataset import DATASET_DIR, read_json, validate_dataset
from src.evaluation.metrics import (
    aggregate_metrics,
    manual_review_template,
    retrieval_metrics,
)
from src.knowledge_base.similarity import cosine_scores, top_indices
from src.utils.artifacts import ArtifactRun, sha256_file, write_json


def evaluate_rankings(questions, rankings, *, min_score=0.5):
    if not np.isfinite(min_score) or not -1 <= min_score <= 1:
        raise ValueError("Invalid cosine threshold")
    records = []
    for question, ranked in zip(questions, rankings, strict=True):
        if question["split"] != "dev":
            raise ValueError("Reserve evaluation is disabled before Q10-B freeze")
        filtered = [hit for hit in ranked if hit["score"] >= min_score]
        prepared = prepare_prompt(
            question["question"], [hit["document"] for hit in filtered]
        )
        records.append(
            {
                "question_id": question["question_id"],
                "question": question["question"],
                "category": question["category"],
                "answerability": question["answerability"],
                "raw_metrics": retrieval_metrics(question, ranked),
                "context_metrics": retrieval_metrics(question, filtered),
                "raw_ranked": ranked,
                "context_chunk_ids": [hit["document"]["chunk_id"] for hit in filtered],
                "empty_context": not filtered,
                "generation_status": "not_run",
                "generation_input": {**prepared.record(), "prompt_sent": False},
                "quality_scores": None,
            }
        )
    return records


def compact_records(records):
    return [
        {
            key: row[key]
            for key in (
                "question_id",
                "category",
                "answerability",
                "raw_metrics",
                "context_metrics",
                "empty_context",
                "context_chunk_ids",
                "generation_status",
                "quality_scores",
            )
        }
        for row in records
    ]


def run_baseline(directory, *, replay=None):
    # Set cache policy before lazy SentenceTransformer loading. This entry point
    # has no generation client and never sends a prompt to a provider.
    os.environ["HF_HUB_OFFLINE"] = "1"
    import torch

    from src.knowledge_base.vector_store import VectorStore

    torch.set_num_threads(1)
    torch.manual_seed(0)
    manifest, _, questions, validation = validate_dataset(directory)
    rows = questions["dev"]
    store = VectorStore()
    store.model.to("cpu")
    queries = [row["question"] for row in rows]
    token_counts = [store.budget.count(query) for query in queries]
    oversized = [
        row["question_id"]
        for row, count in zip(rows, token_counts, strict=True)
        if count > store.budget.limit
    ]
    if oversized:
        raise ValueError(f"Questions exceed the encoder limit: {oversized}")
    dataset_hash = sha256_file(Path(directory) / "manifest.json")
    old = None
    encode_seconds = None
    if replay:
        replay = resolve_path(replay)
        old = read_json(replay / "baseline.json")
        if (
            old["dataset_manifest_sha256"] != dataset_hash
            or old["index_sha256"] != store.index_sha256
            or old["question_ids"] != [row["question_id"] for row in rows]
            or old["embedding"] != store.budget.manifest()
            or old["retrieval_top_k"] != settings.RETRIEVAL_TOP_K
            or old["min_score"] != 0.5
            or old["cutoffs"] != [1, 5, 10]
            or old["prompt_version"] != PROMPT_VERSION
            or old["query_vectors_sha256"] != sha256_file(replay / "query_vectors.npy")
        ):
            raise ValueError("Replay dataset, index, embedding or query vectors differ")
        query_vectors = np.load(replay / "query_vectors.npy", allow_pickle=False)
    else:
        started = time.perf_counter()
        query_vectors = store.encode_texts(
            queries, batch_size=8, show_progress_bar=False, convert_to_numpy=True
        )
        encode_seconds = time.perf_counter() - started
    expected_shape = (len(rows), store.model.get_sentence_embedding_dimension())
    if query_vectors.shape != expected_shape or not np.isfinite(query_vectors).all():
        raise ValueError("Invalid saved query embeddings")
    documents = store.vector_index["documents"]
    rankings = []
    started = time.perf_counter()
    for vector in query_vectors:
        scores = cosine_scores(store.vector_index["vectors"], vector)
        rankings.append(
            [
                {"document": documents[int(index)], "score": float(scores[index])}
                for index in top_indices(scores, settings.RETRIEVAL_TOP_K)
            ]
        )
    scoring_seconds = time.perf_counter() - started
    records = evaluate_rankings(rows, rankings)
    raw = aggregate_metrics(records, "raw_metrics")
    context = aggregate_metrics(records, "context_metrics")
    if old and (
        old["summary"]["raw"] != raw
        or old["summary"]["context"] != context
        or old["results"] != compact_records(records)
        or read_json(replay / "retrieval.json")["records"] != records
    ):
        raise ValueError("Replay changed frozen rankings or metrics")
    summary = {
        "raw": raw,
        "context": context,
        "generation_status": "not_run",
        "live_api_calls": 0,
        "manual_quality_scores": None,
        "unscored_scoped_insufficient_questions": sum(
            row["answerability"] != "answerable" for row in rows
        ),
        "reserve_queries_executed": 0,
        "annotation_quality": "AI draft; domain review pending",
    }
    with ArtifactRun("q10a_replays" if replay else "q10a_baselines") as run:
        np.save(run.path / "query_vectors.npy", query_vectors, allow_pickle=False)
        baseline = {
            "schema": "chemqa-q10a-retrieval-baseline-v1",
            "dataset_version": manifest["version"],
            "dataset_manifest_sha256": dataset_hash,
            "index_sha256": store.index_sha256,
            "embedding": store.budget.manifest(),
            "index_rows": len(documents),
            "retrieval_top_k": settings.RETRIEVAL_TOP_K,
            "min_score": 0.5,
            "cutoffs": [1, 5, 10],
            "device": "cpu",
            "torch_threads": 1,
            "query_batch_size": 8,
            "query_token_counts": token_counts,
            "query_vectors_sha256": sha256_file(run.path / "query_vectors.npy"),
            "question_ids": [row["question_id"] for row in rows],
            "prompt_version": PROMPT_VERSION,
            "timings_seconds": {
                "batch_encoding": encode_seconds,
                "all_query_scoring": scoring_seconds,
            },
            "replayed_from": str(replay) if replay else None,
            "summary": summary,
            "results": compact_records(records),
            "evaluator_sha256": {
                str(path.relative_to(Path(__file__).resolve().parents[1])): sha256_file(
                    path
                )
                for path in [
                    Path(__file__).resolve(),
                    Path(__file__).resolve().parents[1] / "src/evaluation/metrics.py",
                    Path(__file__).resolve().parents[1] / "src/evaluation/dataset.py",
                ]
            },
        }
        write_json(run.path / "retrieval.json", {"records": records})
        write_json(run.path / "baseline.json", baseline)
        write_json(run.path / "manual_review.json", manual_review_template(rows))
        target = run.publish(
            "complete",
            {
                "index_sha256": store.index_sha256,
                "dataset_manifest_sha256": dataset_hash,
                "reserve_queries_executed": 0,
                "generation_requests": 0,
            },
        )
    return {
        "source_validation": validation,
        "artifact_directory": str(target),
        **baseline,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-dir", type=Path, default=DATASET_DIR)
    parser.add_argument(
        "--split",
        choices=["dev"],
        default="dev",
        help="Reserve ranking is disabled until Q10-B",
    )
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--run-baseline", action="store_true")
    action.add_argument(
        "--replay",
        type=Path,
        help="Replay the development baseline from saved query vectors",
    )
    parser.add_argument("--index-dir")
    parser.add_argument("--output-dir")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    configure_paths(index_dir=args.index_dir, output_dir=args.output_dir)
    directory = resolve_path(args.dataset_dir)
    if args.run_baseline or args.replay:
        report = run_baseline(directory, replay=args.replay)
    else:
        _, _, _, report = validate_dataset(directory)
    if args.report:
        write_json(resolve_path(args.report), report)
    print(
        f"Q10-A: source validation passed; generation requests=0; reserve rankings=0. Report: {args.report}"
    )


if __name__ == "__main__":
    main()
