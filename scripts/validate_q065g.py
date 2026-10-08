"""Fixed dev-only BM25/Dense/RRF comparison, profile publication and replay."""

import argparse
import json
import resource
import statistics
import time
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from config.settings import BASE_DIR, configure_paths, resolve_path, settings
from src.evaluation.dataset import validate_dataset
from src.evaluation.metrics import aggregate_metrics, retrieval_metrics
from src.knowledge_base.binary_index import BinaryIndex
from src.knowledge_base.embedding import profile_from_file
from src.knowledge_base.hybrid_search import HybridSearch, fuse_rrf
from src.knowledge_base.lexical_index import (
    FILES,
    analyze,
    build_lexical,
    dense_binding,
)
from src.knowledge_base.vector_store import VectorStore
from src.utils.artifacts import ArtifactRun, sha256_file, write_json

ROOT = Path(BASE_DIR)
PROTOCOL = ROOT / "config/q065g_experiment.json"
MODES = ("dense", "bm25", "hybrid")


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def immutable_files():
    f = read(ROOT / "docs/Q06_5F_FULL.json")
    source = Path(f["artifact_directory"])
    e = Path(f["source_directory"])
    return [
        ROOT / "data/vector_db/vector_index.json",
        ROOT / "data/processed/processed_chunks.json",
        source / "run.json",
        *[source / n for n in ["storage.json", "vectors.npy", "metadata.sqlite3"]],
        e / "query_vectors.npy",
        e / "retrieval.json",
        e / "evaluation.json",
    ]


def fingerprints():
    return {str(p.relative_to(ROOT)): sha256_file(p) for p in immutable_files()}


def load_inputs():
    protocol = read(PROTOCOL)
    if (
        protocol["schema"] != "chemqa-hybrid-experiment-v1"
        or protocol["route_window"] != 50
        or protocol["rrf_constant"] != 60
        or protocol["bm25"] != {"k1": 1.2, "b": 0.75, "query_term_frequency": "binary"}
    ):
        raise ValueError(
            "Experiment protocol changed; define a new experiment explicitly"
        )
    f = read(ROOT / "docs/Q06_5F_FULL.json")
    source = Path(f["artifact_directory"])
    e = Path(f["source_directory"])
    old = read(e / "evaluation.json")
    manifest = read(e / "run.json")
    profile, profile_sha = profile_from_file(ROOT / "config/q065e_embedding.json")
    if (
        profile_sha != old["profile_sha256"]
        or sha256_file(ROOT / "evaluation/manifest.json")
        != old["dataset_manifest_sha256"]
    ):
        raise ValueError("Fixed model/dataset configuration changed")
    for name in ["query_vectors.npy", "retrieval.json", "evaluation.json"]:
        if sha256_file(e / name) != manifest["files"][name]:
            raise ValueError("Frozen E query artifact changed")
    storage = BinaryIndex(
        source,
        expected_embedding={
            **profile,
            "token_count_includes_prompt_and_special_tokens": True,
        },
    )
    _, _, dataset, _ = validate_dataset()
    queries = np.load(e / "query_vectors.npy", allow_pickle=False)
    if queries.shape != (len(dataset["dev"]), profile["dimension"]):
        storage.close()
        raise ValueError("Frozen query matrix mismatch")
    by_question = {
        q["question"]: v for q, v in zip(dataset["dev"], queries, strict=True)
    }
    store = VectorStore.__new__(VectorStore)
    store.storage = storage
    store.encoder = SimpleNamespace(
        encode=lambda text, *, kind: by_question[text] if kind == "query" else None
    )
    store.vector_index = {"documents": storage.documents, "vectors": storage.vectors}
    return store, queries, dataset["dev"], protocol, read(e / "retrieval.json")


def choose_mode(summaries):
    dense = summaries["dense"]["at_k"]
    hybrid = summaries["hybrid"]["at_k"]
    return (
        "hybrid"
        if (
            hybrid["10"]["complete_anchor_recall"]
            > dense["10"]["complete_anchor_recall"]
            and hybrid["5"]["mean_anchor_character_coverage"]
            >= dense["5"]["mean_anchor_character_coverage"]
            and hybrid["10"]["annotated_doc_recall"]
            >= dense["10"]["annotated_doc_recall"]
        )
        else "dense"
    )


def overlap_pairs(hits):
    count = 0
    for i, left in enumerate(hits):
        for right in hits[i + 1 :]:
            a, b = left["document"], right["document"]
            if a["doc_id"] == b["doc_id"] and any(
                x["page_number"] == y["page_number"]
                and max(x["char_start"], y["char_start"])
                < min(x["char_end"], y["char_end"])
                for x in a.get("source_spans", [])
                for y in b.get("source_spans", [])
            ):
                count += 1
    return count


def duplicate_diagnostics(hits):
    docs = Counter(hit["document"]["doc_id"] for hit in hits)
    return {
        "hits": len(hits),
        "unique_papers": len(docs),
        "additional_chunks_from_already_hit_papers": len(hits) - len(docs),
        "largest_paper_fraction": max(docs.values(), default=0) / len(hits)
        if hits
        else 0,
        "source_overlap_pairs": overlap_pairs(hits),
    }


def compact(hits):
    return [
        {
            "rank": rank,
            "row_id": hit["row_id"],
            "chunk_id": hit["document"]["chunk_id"],
            "doc_id": hit["document"]["doc_id"],
            "score": hit["score"],
            "score_kind": hit["score_kind"],
            **({"routes": hit["routes"]} if "routes" in hit else {}),
        }
        for rank, hit in enumerate(hits, 1)
    ]


def evaluate(store, queries, questions, lexical, protocol, frozen):
    engine = HybridSearch(
        store,
        lexical,
        window=protocol["route_window"],
        constant=protocol["rrf_constant"],
    )
    records = []
    top10_records = {m: [] for m in MODES}
    pool_records = {m: [] for m in MODES}
    for q, vector, old in zip(questions, queries, frozen["records"], strict=True):
        if q["split"] != "dev" or q["question_id"] != old["question_id"]:
            raise ValueError("Reserve queries or changed question order forbidden")
        routes = engine.routes(q["question"], query_vector=vector)
        if [h["document"]["chunk_id"] for h in routes["dense"][:10]] != [
            h["document"]["chunk_id"] for h in old["raw_ranked"]
        ]:
            raise ValueError("Frozen dense baseline changed")
        metrics = {m: retrieval_metrics(q, routes[m][:10]) for m in MODES}
        pool = {m: retrieval_metrics(q, routes[m], cutoffs=(50,)) for m in MODES}
        for mode in MODES:
            top10_records[mode].append({"metrics": metrics[mode]})
            pool_records[mode].append({"metrics": pool[mode]})
        terms = sorted(set(analyze(q["question"])))
        matched = [term for term in terms if term in engine.lexical.vocabulary]
        records.append(
            {
                "question_id": q["question_id"],
                "category": q["category"],
                "answerability": q["answerability"],
                "top10_metrics": metrics,
                "candidate_pool_metrics_at_50": pool,
                "rankings": {m: compact(routes[m]) for m in MODES},
                "query_terms": terms,
                "matched_corpus_terms": matched,
                "cjk_terms": sum(t.startswith("c:") for t in terms),
                "matched_cjk_terms": sum(t.startswith("c:") for t in matched),
                "route_union_before_final_window": len(
                    {
                        h["document"]["chunk_id"]
                        for m in ["dense", "bm25"]
                        for h in routes[m]
                    }
                ),
                "shared_route_candidates": len(
                    {h["document"]["chunk_id"] for h in routes["dense"]}
                    & {h["document"]["chunk_id"] for h in routes["bm25"]}
                ),
                "duplicate_diagnostics_at_10": {
                    m: duplicate_diagnostics(routes[m][:10]) for m in MODES
                },
            }
        )
    summaries = {m: aggregate_metrics(top10_records[m], "metrics") for m in MODES}
    if summaries["dense"] != frozen["summary"]:
        raise ValueError("Dense metrics differ from E")
    return {
        "records": records,
        "summary_top10": summaries,
        "summary_candidate_pool_at_50": {
            m: aggregate_metrics(pool_records[m], "metrics") for m in MODES
        },
        "selected_mode": choose_mode(summaries),
    }, engine


def benchmark(engine, queries, questions):
    samples = {m: [] for m in MODES}
    fusion = []
    for _ in range(5):
        for question, vector in zip(questions, queries, strict=True):
            start = time.perf_counter()
            dense = engine.vector_store.storage.search(vector, engine.window)
            dense = [
                {
                    **h,
                    "row_id": engine.row_order[h["document"]["chunk_id"]],
                    "score_kind": "cosine",
                }
                for h in dense
            ]
            d = time.perf_counter() - start
            start = time.perf_counter()
            bm25 = engine.lexical.search(question["question"], engine.window)
            b = time.perf_counter() - start
            start = time.perf_counter()
            fuse_rrf(
                {"dense": dense, "bm25": bm25},
                engine.row_order,
                constant=engine.constant,
            )
            f = time.perf_counter() - start
            samples["dense"].append(d)
            samples["bm25"].append(b)
            samples["hybrid"].append(d + b + f)
            fusion.append(f)
    return {
        "per_mode": {
            m: {
                "samples": len(v),
                "median_ms": statistics.median(v) * 1000,
                "p95_ms": float(np.percentile(v, 95)) * 1000,
            }
            for m, v in samples.items()
        },
        "fusion_median_ms": statistics.median(fusion) * 1000,
        "query_encoding_included": False,
        "method": "5 cycles of 20 frozen dev queries, same loaded indexes, each route fetches up to 50 metadata records; hybrid time is measured serial dense+BM25+fusion sum. BLAS threads controlled by caller. Single-machine warm observations, no end-to-end claim.",
    }


def failure_report(evaluation):
    comparisons = []
    for row in evaluation["records"]:
        if row["answerability"] != "answerable":
            continue
        d = row["top10_metrics"]["dense"]["at_k"]["10"]
        h = row["top10_metrics"]["hybrid"]["at_k"]["10"]
        b = row["top10_metrics"]["bm25"]["at_k"]["10"]
        comparisons.append(
            {
                "question_id": row["question_id"],
                "category": row["category"],
                "complete_anchor_recall_at_10": {
                    "dense": d["complete_anchor_recall"],
                    "bm25": b["complete_anchor_recall"],
                    "hybrid": h["complete_anchor_recall"],
                },
                "hybrid_minus_dense": h["complete_anchor_recall"]
                - d["complete_anchor_recall"],
                "selected_anchor_coverage": row["top10_metrics"][
                    evaluation["selected_mode"]
                ]["at_k"]["10"]["anchor_coverage"],
                "cjk_terms": row["cjk_terms"],
                "matched_cjk_terms": row["matched_cjk_terms"],
                "matched_corpus_terms": row["matched_corpus_terms"],
            }
        )
    return {
        "schema": "chemqa-q065g-failures-v1",
        "annotation_quality": "AI draft; domain review pending",
        "selected_mode": evaluation["selected_mode"],
        "improved_questions": [r for r in comparisons if r["hybrid_minus_dense"] > 0],
        "regressed_questions": [r for r in comparisons if r["hybrid_minus_dense"] < 0],
        "selected_incomplete_questions": [
            r
            for r in comparisons
            if any(v < 1 for v in r["selected_anchor_coverage"].values())
        ],
        "per_question_comparison": comparisons,
        "interpretation": "Annotated spans only; unjudged hits are not negatives. No scientific-answer quality assessment or synonym/translation tuning from these errors.",
    }


def run():
    before = fingerprints()
    protocol_sha = sha256_file(PROTOCOL)
    store, queries, questions, protocol, frozen = load_inputs()
    try:
        start = time.perf_counter()
        with ArtifactRun("lexical_indexes") as artifact:
            spec = build_lexical(
                artifact.path,
                store.storage.documents,
                dense_binding(store.storage),
                **{k: protocol["bm25"][k] for k in ["k1", "b"]},
            )
            # Re-read and validate arrays before publishing.
            from src.knowledge_base.lexical_index import BM25Index

            BM25Index(
                artifact.path,
                store.storage.documents,
                dense_binding(store.storage),
                staging=True,
            )
            lexical = artifact.publish(
                "ready",
                {
                    "files": {
                        name: sha256_file(artifact.path / name) for name in FILES
                    },
                    "binding": dense_binding(store.storage),
                    "protocol_sha256": protocol_sha,
                },
            )
        build_seconds = time.perf_counter() - start
        evaluation, engine = evaluate(
            store, queries, questions, lexical, protocol, frozen
        )
        timings = benchmark(engine, queries, questions)
        with ArtifactRun("hybrid_runs") as artifact:
            profile = {
                "schema": "chemqa-retrieval-profile-v1",
                "mode": evaluation["selected_mode"],
                "binding": dense_binding(store.storage),
                "lexical_directory": str(lexical),
                "lexical_run_sha256": sha256_file(lexical / "run.json"),
                "route_window": protocol["route_window"],
                "rrf_constant": protocol["rrf_constant"],
                "fusion": "equal_weight_rrf",
                "deduplication": protocol["deduplication"],
                "score_policy": "raw_only_no_context_threshold",
                "protocol_sha256": protocol_sha,
            }
            write_json(artifact.path / "retrieval_profile.json", profile)
            write_json(artifact.path / "rankings.json", evaluation)
            write_json(artifact.path / "benchmark.json", timings)
            target = artifact.publish(
                "ready",
                {
                    "files": {
                        n: sha256_file(artifact.path / n)
                        for n in [
                            "retrieval_profile.json",
                            "rankings.json",
                            "benchmark.json",
                        ]
                    },
                    "binding": dense_binding(store.storage),
                    "protocol_sha256": protocol_sha,
                    "dataset_manifest_sha256": sha256_file(
                        ROOT / "evaluation/manifest.json"
                    ),
                },
            )
        if before != fingerprints() or protocol_sha != sha256_file(PROTOCOL):
            raise ValueError("Immutable inputs or protocol changed")
        report = {
            "schema": "chemqa-q065g-evaluation-v1",
            "status": "passed",
            "artifact_directory": str(target),
            "retrieval_profile": str(target / "retrieval_profile.json"),
            "lexical_directory": str(lexical),
            "source_dense_directory": str(store.storage.directory),
            "protocol": protocol,
            "protocol_sha256": protocol_sha,
            "dataset_manifest_sha256": sha256_file(ROOT / "evaluation/manifest.json"),
            "rows": len(store.storage.documents),
            "lexical_statistics": spec,
            "lexical_build_and_validation_seconds": build_seconds,
            "lexical_files_bytes": {n: (lexical / n).stat().st_size for n in FILES},
            "summary_top10": evaluation["summary_top10"],
            "summary_candidate_pool_at_50": evaluation["summary_candidate_pool_at_50"],
            "selected_mode": evaluation["selected_mode"],
            "candidate_hybrid_enabled": evaluation["selected_mode"] == "hybrid",
            "production_default_switched": False,
            "timings": timings,
            "duplicate_diagnostics_at_10": {
                m: {
                    key: statistics.mean(
                        row["duplicate_diagnostics_at_10"][m][key]
                        for row in evaluation["records"]
                    )
                    for key in [
                        "unique_papers",
                        "additional_chunks_from_already_hit_papers",
                        "largest_paper_fraction",
                        "source_overlap_pairs",
                    ]
                }
                for m in MODES
            },
            "chinese_query_diagnostics": {
                "queries_with_cjk_terms": sum(
                    row["cjk_terms"] > 0 for row in evaluation["records"]
                ),
                "queries_with_no_matched_cjk_terms": sum(
                    row["cjk_terms"] > 0 and row["matched_cjk_terms"] == 0
                    for row in evaluation["records"]
                ),
            },
            "annotation_quality": "AI draft; domain review pending",
            "rss_high_water_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            "input_fingerprints_before": before,
            "input_fingerprints_after": fingerprints(),
            "generation_requests": 0,
            "query_reencoding_count": 0,
            "reserve_queries_executed": 0,
        }
        write_json(ROOT / "docs/Q06_5G_FULL.json", report)
        write_json(ROOT / "docs/Q06_5G_FAILURES.json", failure_report(evaluation))
        print(
            json.dumps(
                {
                    "status": "passed",
                    "selected_mode": evaluation["selected_mode"],
                    "artifact_directory": str(target),
                    "summaries": {
                        m: evaluation["summary_top10"][m]["at_k"]["10"] for m in MODES
                    },
                },
                indent=2,
            )
        )
    finally:
        store.storage.close()


def replay(directory):
    before = fingerprints()
    manifest = read(directory / "run.json")
    if (
        manifest["status"] != "ready"
        or manifest["kind"] != "hybrid_runs"
        or manifest["protocol_sha256"] != sha256_file(PROTOCOL)
        or manifest["dataset_manifest_sha256"]
        != sha256_file(ROOT / "evaluation/manifest.json")
    ):
        raise ValueError("Frozen retrieval run/profile/dataset mismatch")
    for name, checksum in manifest["files"].items():
        if sha256_file(directory / name) != checksum:
            raise ValueError("Frozen retrieval artifact checksum mismatch")
    store, queries, questions, protocol, frozen = load_inputs()
    try:
        engine = HybridSearch.from_profile(store, directory / "retrieval_profile.json")
        actual, _ = evaluate(
            store,
            queries,
            questions,
            Path(read(directory / "retrieval_profile.json")["lexical_directory"]),
            protocol,
            frozen,
        )
        if actual != read(directory / "rankings.json"):
            raise ValueError("Hybrid replay changed route rankings or metrics")
        public_equal = all(
            [h["document"]["chunk_id"] for h in engine.search(q["question"], 10)]
            == [h["chunk_id"] for h in row["rankings"][engine.mode][:10]]
            for q, row in zip(questions, actual["records"], strict=True)
        )
        if not public_equal or before != fingerprints():
            raise ValueError("Public replay or input preservation failed")
        write_json(
            ROOT / "docs/Q06_5G_REPLAY.json",
            {
                "status": "passed",
                "artifact_directory": str(directory),
                "mode": engine.mode,
                "all_route_scores_rankings_metrics_exactly_equal": True,
                "public_selected_profile_top10_equal_using_frozen_vectors": public_equal,
                "immutable_inputs_unchanged": True,
                "query_reencoding_count": 0,
                "reserve_queries_executed": 0,
                "generation_requests": 0,
            },
        )
    finally:
        store.storage.close()


def runtime_smoke(directory, device):
    from src.knowledge_base.retriever import Retriever

    before = fingerprints()
    profile = read(directory / "retrieval_profile.json")
    f = read(ROOT / "docs/Q06_5F_FULL.json")
    settings.EMBEDDING_PROFILE = str(ROOT / "config/q065e_embedding.json")
    configure_paths(index_dir=f["artifact_directory"])
    store = VectorStore(device=device)
    try:
        engine = HybridSearch.from_profile(store, directory / "retrieval_profile.json")
        retriever = Retriever.__new__(Retriever)
        retriever.vector_store, retriever.raw_search = store, engine
        _, _, dataset, _ = validate_dataset()
        expected = {
            row["question_id"]: row
            for row in read(directory / "rankings.json")["records"]
        }
        checks = []
        for question in dataset["dev"]:
            if question["question_id"] not in {"D01", "D03"}:
                continue
            hits = retriever.search(question["question"], 10)
            frozen = expected[question["question_id"]]["rankings"][profile["mode"]][:10]
            equal = [hit["document"]["chunk_id"] for hit in hits] == [
                hit["chunk_id"] for hit in frozen
            ]
            checks.append(
                {
                    "question_id": question["question_id"],
                    "top10_equal": equal,
                    "score_kinds": sorted({hit["score_kind"] for hit in hits}),
                }
            )
        if (
            len(checks) != 2
            or not all(row["top10_equal"] for row in checks)
            or before != fingerprints()
        ):
            raise ValueError(
                "Real query runtime smoke changed selected rankings or inputs"
            )
        report = {
            "status": "passed",
            "mode": profile["mode"],
            "candidate_directory": str(directory),
            "actual_encoder_device": str(store.model.device),
            "actual_parameter_dtype": str(next(store.model.parameters()).dtype),
            "queries": checks,
            "query_reencoding_count": 2,
            "generation_requests": 0,
            "reserve_queries_executed": 0,
            "immutable_inputs_unchanged": True,
        }
    finally:
        store.storage.close()
    write_json(ROOT / "docs/Q06_5G_RUNTIME.json", report)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["run", "replay", "runtime"])
    parser.add_argument("--candidate", type=Path)
    parser.add_argument("--device", choices=["auto", "cpu", "mps"], default="auto")
    args = parser.parse_args()
    if args.mode == "run":
        run()
    elif args.candidate:
        if args.mode == "runtime":
            runtime_smoke(resolve_path(args.candidate), args.device)
        else:
            replay(resolve_path(args.candidate))
    else:
        parser.error("replay requires --candidate")


if __name__ == "__main__":
    main()
