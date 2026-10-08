"""Migrate the frozen E candidate without encoding; validate exact retrieval and rollback."""

import argparse
import importlib.metadata
import json
import os
import resource
import statistics
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from config.settings import BASE_DIR, configure_paths, resolve_path, settings
from src.evaluation.dataset import validate_dataset
from src.evaluation.metrics import aggregate_metrics, retrieval_metrics
from src.knowledge_base.binary_index import (
    FILES,
    BinaryIndex,
    documents_digest,
    vectors_digest,
    write_binary_index,
)
from src.knowledge_base.embedding import profile_from_file
from src.knowledge_base.similarity import cosine_scores, top_indices
from src.knowledge_base.vector_store import VectorStore
from src.utils.artifacts import ArtifactRun, sha256_file, write_json

ROOT = Path(BASE_DIR)
PROFILE = ROOT / "config/q065e_embedding.json"
BASELINES = [
    ROOT / "data/vector_db/vector_index.json",
    ROOT / "data/processed/processed_chunks.json",
]


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def fingerprints():
    return {str(p.relative_to(ROOT)): sha256_file(p) for p in BASELINES}


def verified_source(source):
    manifest = read(source / "run.json")
    if (
        manifest.get("schema") != "chemqa-artifact-run-v1"
        or manifest.get("kind") != "indexes"
        or manifest.get("status") != "ready"
    ):
        raise ValueError("Source E candidate is not ready")
    required = {
        "vector_index.json",
        "processed_chunks.json",
        "query_vectors.npy",
        "retrieval.json",
        "evaluation.json",
    }
    if not required.issubset(manifest.get("files", {})):
        raise ValueError("Source candidate is incomplete")
    for name in required:
        if manifest["files"][name] != sha256_file(source / name):
            raise ValueError("Source E file checksum mismatch")
    evaluation = read(source / "evaluation.json")
    profile, checksum = profile_from_file(PROFILE)
    if evaluation["profile_sha256"] != checksum or evaluation[
        "dataset_manifest_sha256"
    ] != sha256_file(ROOT / "evaluation/manifest.json"):
        raise ValueError("Frozen profile/dataset changed")
    index = read(source / "vector_index.json")
    if index["embedding"] != {
        **profile,
        "token_count_includes_prompt_and_special_tokens": True,
    }:
        raise ValueError("Source model profile mismatch")
    queries = np.load(source / "query_vectors.npy", allow_pickle=False)
    _, _, dataset, _ = validate_dataset()
    questions = dataset["dev"]
    if queries.shape != (len(questions), profile["dimension"]):
        raise ValueError("Source query rows mismatch")
    return index, queries, questions, manifest, evaluation


def check_retrieval(binary, index, queries, questions, saved):
    records = []
    max_error = 0.0
    exact = True
    for q, query, old in zip(questions, queries, saved["records"], strict=True):
        if q["split"] != "dev" or q["question_id"] != old["question_id"]:
            raise ValueError("Only frozen development queries may execute")
        reference = cosine_scores(index["vectors"], query)
        expected = top_indices(reference, 10)
        ranked = binary.search(query, 10)
        exact &= (
            [r["document"]["chunk_id"] for r in ranked]
            == [index["documents"][i]["chunk_id"] for i in expected]
            == [r["document"]["chunk_id"] for r in old["raw_ranked"]]
        )
        for row, hit in zip(expected, ranked, strict=True):
            max_error = max(max_error, abs(float(reference[row]) - hit["score"]))
        records.append(
            {
                "question_id": q["question_id"],
                "raw_metrics": retrieval_metrics(q, ranked),
            }
        )
    summary = aggregate_metrics(records, "raw_metrics")
    metrics_equal = summary == saved["summary"] and all(
        r["raw_metrics"] == o["raw_metrics"]
        for r, o in zip(records, saved["records"], strict=True)
    )
    if not exact or not metrics_equal or max_error > 2e-6:
        raise ValueError("Binary retrieval differs from frozen cosine reference")
    return {
        "query_count": len(queries),
        "top10_ids_and_order_equal": exact,
        "per_question_and_aggregate_metrics_equal": metrics_equal,
        "max_top10_score_absolute_error": max_error,
        "score_absolute_tolerance": 2e-6,
        "summary": summary,
        "reserve_queries_executed": 0,
        "generation_requests": 0,
    }


def load_json_store(source, embedding):
    configure_paths(index_dir=source)
    store = VectorStore.__new__(VectorStore)
    store.encoder = SimpleNamespace(profile=embedding)
    store.budget = SimpleNamespace(manifest=lambda: embedding)
    store.vector_index = store._load_vector_index()
    return store


def benchmark_worker(backend, candidate, source, report):

    embedding = read(source / "evaluation.json")["embedding"]
    queries = np.load(source / "query_vectors.npy", allow_pickle=False)
    start = time.perf_counter()
    if backend == "binary":
        store = BinaryIndex(candidate, expected_embedding=embedding)
        search = lambda query: store.search(query, 10)
    else:
        store = load_json_store(source, embedding)

        def search(query):
            scores = cosine_scores(store.vector_index["vectors"], query)
            return [
                {
                    "document": dict(store.vector_index["documents"][i]),
                    "score": float(scores[i]),
                }
                for i in top_indices(scores, 10)
            ]

    load_seconds = time.perf_counter() - start
    for query in queries[:3]:
        search(query)
    times = []
    for _ in range(5):
        for query in queries:
            start = time.perf_counter()
            search(query)
            times.append(time.perf_counter() - start)
    write_json(
        report,
        {
            "backend": backend,
            "load_seconds": load_seconds,
            "rss_high_water_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            "query_samples": len(times),
            "query_median_ms": statistics.median(times) * 1000,
            "query_p95_ms": float(np.percentile(times, 95)) * 1000,
            "blas_threads": 1,
            "query_encoding_included": False,
            "filesystem_cache": "warm or uncontrolled; not cold disk benchmark",
        },
    )
    if backend == "binary":
        store.close()


def benchmark(candidate, source):
    records = []
    env = {
        **os.environ,
        "OMP_NUM_THREADS": "1",
        "OPENBLAS_NUM_THREADS": "1",
        "VECLIB_MAXIMUM_THREADS": "1",
        "MKL_NUM_THREADS": "1",
    }
    with ArtifactRun("q065f_benchmarks") as run:
        for repeat in range(3):
            for backend in ["json", "binary"]:
                result = run.path / f"{backend}-{repeat}.json"
                subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "scripts.validate_q065f",
                        "worker",
                        "--source",
                        str(source),
                        "--candidate",
                        str(candidate),
                        "--backend",
                        backend,
                        "--report",
                        str(result),
                    ],
                    cwd=ROOT,
                    env=env,
                    check=True,
                    stdout=subprocess.DEVNULL,
                )
                records.append(read(result))
        summary = {
            backend: {
                key: statistics.median(
                    r[key] for r in records if r["backend"] == backend
                )
                for key in [
                    "load_seconds",
                    "rss_high_water_bytes",
                    "query_median_ms",
                    "query_p95_ms",
                ]
            }
            for backend in ["json", "binary"]
        }
        report = {
            "schema": "chemqa-q065f-benchmark-v1",
            "records": records,
            "median_of_three_processes": summary,
            "source_directory": str(source),
            "candidate_directory": str(candidate),
            "method": "3 fresh processes per backend; all integrity/profile checks included in load, model loading and query encoding excluded; 3 warmup then 5 x 20 single-query searches; BLAS threads fixed at 1. Filesystem cache uncontrolled; single-machine observations, not a general speed claim.",
        }
        write_json(run.path / "benchmark.json", report)
        target = run.publish(
            "complete", {"generation_requests": 0, "reserve_queries_executed": 0}
        )
    write_json(
        ROOT / "docs/Q06_5F_BENCHMARK.json",
        {**report, "artifact_directory": str(target)},
    )
    return report


def migrate(source):
    before = fingerprints()
    source_before = {
        name: sha256_file(source / name)
        for name in [
            "run.json",
            *[
                "vector_index.json",
                "processed_chunks.json",
                "query_vectors.npy",
                "retrieval.json",
                "evaluation.json",
            ],
        ]
    }
    index, queries, questions, manifest, evaluation = verified_source(source)
    start = time.perf_counter()
    with ArtifactRun("indexes") as run:
        spec = write_binary_index(
            run.path,
            index,
            source={
                "directory": str(source),
                "run_sha256": source_before["run.json"],
                "files": manifest["files"],
            },
        )
        write_seconds = time.perf_counter() - start
        binary = BinaryIndex(
            run.path, expected_embedding=index["embedding"], staging=True
        )
        try:
            documents_equal = list(binary.documents) == index["documents"]
            vectors_equal = np.array_equal(
                binary.vectors, np.asarray(index["vectors"], dtype=np.float32)
            )
            if not documents_equal or not vectors_equal:
                raise ValueError("Migration modified fixed documents or vectors")
            retrieval = check_retrieval(
                binary, index, queries, questions, read(source / "retrieval.json")
            )
        finally:
            binary.close()
        files = {name: sha256_file(run.path / name) for name in FILES}
        target = run.publish(
            "ready",
            {
                "storage_backend": spec["backend"],
                "files": files,
                "embedding": index["embedding"],
                "chunking": index["chunking"],
                "corpus_sha256": index["corpus_sha256"],
                "source": spec["source"],
                "validation": {
                    "documents_equal": documents_equal,
                    "float32_vectors_bitwise_equal": vectors_equal,
                    "row_count": spec["row_count"],
                    "retrieval": retrieval,
                },
            },
        )
    # Reopen only through the immutable published-loader path.
    loaded = BinaryIndex(target, expected_embedding=index["embedding"])
    try:
        reloaded = check_retrieval(
            loaded, index, queries, questions, read(source / "retrieval.json")
        )
    finally:
        loaded.close()
    # Re-select JSON explicitly to verify rollback through the application loader.
    legacy = load_json_store(source, index["embedding"])
    rollback = legacy.vector_index["documents"] == index[
        "documents"
    ] and np.array_equal(legacy.vector_index["vectors"], np.asarray(index["vectors"]))
    rollback_ids_equal = all(
        [
            legacy.vector_index["documents"][i]["chunk_id"]
            for i in top_indices(
                cosine_scores(legacy.vector_index["vectors"], query), 10
            )
        ]
        == [hit["document"]["chunk_id"] for hit in row["raw_ranked"]]
        for query, row in zip(
            queries, read(source / "retrieval.json")["records"], strict=True
        )
    )
    after = fingerprints()
    source_unchanged = all(
        sha256_file(source / name) == value for name, value in source_before.items()
    )
    if (
        before != after
        or not source_unchanged
        or not rollback
        or not rollback_ids_equal
    ):
        raise ValueError("Source preservation/rollback failed")
    report = {
        "schema": "chemqa-q065f-storage-v1",
        "status": "passed",
        "artifact_directory": str(target),
        "source_directory": str(source),
        "source_files_sha256": source_before,
        "backend": spec["backend"],
        "rows": spec["row_count"],
        "dimension": spec["dimension"],
        "embedding": index["embedding"],
        "chunking": index["chunking"],
        "source_validation_inherited": evaluation["validation"],
        "documents_equal": documents_equal,
        "float32_vectors_bitwise_equal": vectors_equal,
        "documents_sha256": documents_digest(index["documents"]),
        "float32_vectors_sha256": vectors_digest(binary.vectors),
        "published_checksums_verified": True,
        "retrieval": retrieval,
        "reloaded_retrieval": reloaded,
        "rollback_json_loaded_exactly": rollback,
        "rollback_top10_ids_equal": rollback_ids_equal,
        "source_unchanged": source_unchanged,
        "baseline_before": before,
        "baseline_after": after,
        "migration_write_seconds": write_seconds,
        "source_index_bytes": (source / "vector_index.json").stat().st_size,
        "binary_files_bytes": {name: (target / name).stat().st_size for name in FILES},
        "versions": {p: importlib.metadata.version(p) for p in ["numpy"]},
        "sqlite_version": __import__("sqlite3").sqlite_version,
        "default_switched": False,
        "query_reencoding_count": 0,
        "generation_requests": 0,
        "reserve_queries_executed": 0,
        "annotation_quality": "AI draft; domain review pending",
    }
    write_json(ROOT / "docs/Q06_5F_FULL.json", report)
    print(
        json.dumps(
            {
                "status": "passed",
                "artifact_directory": str(target),
                "max_score_error": retrieval["max_top10_score_absolute_error"],
            },
            indent=2,
        )
    )
    benchmark(target, source)


def replay(candidate, source):
    before = fingerprints()
    index, queries, questions, _, _ = verified_source(source)
    binary = BinaryIndex(candidate, expected_embedding=index["embedding"])
    try:
        retrieval = check_retrieval(
            binary, index, queries, questions, read(source / "retrieval.json")
        )
        metadata_equal = list(binary.documents) == index["documents"]
        vectors_equal = np.array_equal(
            binary.vectors, np.asarray(index["vectors"], dtype=np.float32)
        )
    finally:
        binary.close()
    configure_paths(index_dir=candidate)
    store = VectorStore.__new__(VectorStore)
    by_question = {
        q["question"]: vector for q, vector in zip(questions, queries, strict=True)
    }
    store.encoder = SimpleNamespace(
        manifest=lambda: index["embedding"],
        encode=lambda text, *, kind: by_question[text] if kind == "query" else None,
    )
    store.vector_index = store._load_vector_index()
    try:
        public_equal = all(
            [
                hit["document"]["chunk_id"]
                for hit in store.similarity_search(q["question"], 10)
            ]
            == [hit["document"]["chunk_id"] for hit in row["raw_ranked"]]
            for q, row in zip(
                questions, read(source / "retrieval.json")["records"], strict=True
            )
        )
    finally:
        store.storage.close()
    if (
        not metadata_equal
        or not vectors_equal
        or not public_equal
        or before != fingerprints()
    ):
        raise ValueError("Replay content/preservation failure")
    write_json(
        ROOT / "docs/Q06_5F_REPLAY.json",
        {
            "status": "passed",
            "candidate_directory": str(candidate),
            "retrieval": retrieval,
            "documents_equal": metadata_equal,
            "float32_vectors_bitwise_equal": vectors_equal,
            "baseline_unchanged": True,
            "public_vector_store_top10_equal_using_frozen_query_vectors": public_equal,
            "query_reencoding_count": 0,
            "generation_requests": 0,
            "reserve_queries_executed": 0,
        },
    )


def runtime_smoke(candidate, source, device):
    import torch

    before = fingerprints()
    matrix = torch.ones((32, 32))
    if float((matrix @ matrix).sum()) != 32768.0:
        raise ValueError("Active PyTorch computation failed")
    settings.EMBEDDING_PROFILE = str(PROFILE)
    configure_paths(index_dir=candidate)
    store = VectorStore(device=device)
    try:
        question = read(ROOT / "evaluation/dev.json")["questions"][0]
        hits = store.similarity_search(question["question"], 10)
        saved = read(source / "retrieval.json")["records"][0]
        equal = [h["document"]["chunk_id"] for h in hits] == [
            h["document"]["chunk_id"] for h in saved["raw_ranked"]
        ]
        if (
            question["question_id"] != saved["question_id"]
            or not equal
            or before != fingerprints()
        ):
            raise ValueError("Application runtime smoke changed ranking or baseline")
        report = {
            "status": "passed",
            "backend": store.storage.spec["backend"],
            "candidate_directory": str(candidate),
            "active_torch_cpu_computation_passed": True,
            "actual_encoder_device": str(store.model.device),
            "actual_parameter_dtype": str(next(store.model.parameters()).dtype),
            "question_id": question["question_id"],
            "public_top10_equal_to_E": equal,
            "query_reencoding_count": 1,
            "generation_requests": 0,
            "reserve_queries_executed": 0,
            "baseline_unchanged": True,
        }
    finally:
        store.storage.close()
    write_json(ROOT / "docs/Q06_5F_RUNTIME.json", report)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["migrate", "replay", "runtime", "worker"])
    parser.add_argument("--source", type=Path)
    parser.add_argument("--candidate", type=Path)
    parser.add_argument("--backend", choices=["json", "binary"])
    parser.add_argument("--device", choices=["auto", "cpu", "mps"], default="auto")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    source = resolve_path(
        args.source or read(ROOT / "docs/Q06_5E_FULL.json")["artifact_directory"]
    )
    if args.mode == "migrate":
        migrate(source)
    elif args.mode == "runtime":
        if not args.candidate:
            parser.error("runtime requires --candidate")
        runtime_smoke(resolve_path(args.candidate), source, args.device)
    elif args.mode == "replay":
        if not args.candidate:
            parser.error("replay requires --candidate")
        replay(resolve_path(args.candidate), source)
    else:
        if not all([args.candidate, args.backend, args.report]):
            parser.error("worker requires --candidate, --backend and --report")
        benchmark_worker(
            args.backend,
            resolve_path(args.candidate),
            source,
            resolve_path(args.report),
        )


if __name__ == "__main__":
    main()
