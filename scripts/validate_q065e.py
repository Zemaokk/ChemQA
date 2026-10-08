"""Freeze local text, compare controlled candidates, and publish a separate index."""

import argparse
import gc
import hashlib
import importlib.metadata
import json
import resource
import time
from pathlib import Path

import numpy as np
import pymupdf

from config.settings import BASE_DIR
from scripts.validate_q02 import validate as validate_locations
from src.evaluation.dataset import validate_dataset
from src.evaluation.metrics import aggregate_metrics, retrieval_metrics
from src.knowledge_base.embedding import CandidateEncoder, profile_from_file
from src.knowledge_base.identity import document_id, unique_chunks
from src.knowledge_base.paragraph_processor import ParagraphProcessor
from src.knowledge_base.pdf_loader import PDFLoader
from src.knowledge_base.similarity import cosine_scores, top_indices
from src.utils.artifacts import ArtifactRun, config_record, sha256_file, write_json

ROOT = Path(BASE_DIR)
PROFILE = ROOT / "config/q065e_embedding.json"
PROTOCOL = ROOT / "config/q065e_experiment.json"
RESOURCE_COUNTERS = {
    "mps_driver_max_sampled_bytes": 0,
    "mps_driver_max_after_cache_clear_bytes": 0,
}
BASELINES = [
    ROOT / "data/vector_db/vector_index.json",
    ROOT / "data/processed/processed_chunks.json",
]


def runtime_config(encoder):
    return {
        **config_record(),
        "embedding_model": encoder.profile["model"],
        "embedding_revision": encoder.profile["revision"],
        "embedding_profile": str(PROFILE.relative_to(ROOT)),
    }


def fingerprints():
    return {str(p.relative_to(ROOT)): sha256_file(p) for p in BASELINES}


def corpus_freeze():
    before = fingerprints()
    loader = PDFLoader()
    by_id, diagnostics = {}, []
    for source in loader.load_pdfs():
        documents = loader.load_pdf(source)
        if len(documents) != 1:
            raise ValueError(f"Cannot freeze extraction: {source}")
        doc = documents[0]
        doc_id = doc["metadata"]["doc_id"]
        doc["metadata"]["source"] = str(Path(source).relative_to(ROOT))
        if doc_id in by_id:
            by_id[doc_id]["metadata"]["sources"].append(doc["metadata"]["source"])
            continue
        doc["metadata"]["sources"] = [doc["metadata"]["source"]]
        doc["paragraph_ends"] = []
        with pymupdf.open(source) as pdf:
            for page, original in zip(pdf, doc["pages"], strict=True):
                blocks = [
                    b[4] for b in page.get_text("blocks", sort=False) if b[6] == 0
                ]
                if "".join(blocks) == original["text"]:
                    cursor = original["char_start"]
                    for block in blocks:
                        cursor += len(block)
                        doc["paragraph_ends"].append(cursor)
                else:
                    diagnostics.append(
                        {
                            "doc_id": doc_id,
                            "page_number": original["page_number"],
                            "reason": "block_text_does_not_reconstruct_frozen_page; use_page_boundary_only",
                        }
                    )
                doc["paragraph_ends"].append(original["char_end"])
        by_id[doc_id] = doc
    documents = [by_id[key] for key in sorted(by_id)]
    with ArtifactRun("q065e_corpus") as artifact:
        write_json(artifact.path / "documents.json", {"documents": documents})
        summary = {
            "schema": "chemqa-q065e-corpus-v1",
            "document_count": len(documents),
            "physical_file_count": len(loader.load_pdfs()),
            "physical_pages_unique_documents": sum(len(d["pages"]) for d in documents),
            "extraction": documents[0]["extraction"],
            "block_hints_are_semantic_paragraphs": False,
            "block_hint_fallbacks": diagnostics,
            "documents_sha256": sha256_file(artifact.path / "documents.json"),
            "source_documents": [
                {
                    "doc_id": d["metadata"]["doc_id"],
                    "sources": d["metadata"]["sources"],
                    "raw_text_sha256": hashlib.sha256(d["text"].encode()).hexdigest(),
                }
                for d in documents
            ],
            "baseline_before": before,
            "baseline_after": fingerprints(),
            "generation_requests": 0,
        }
        if before != summary["baseline_after"]:
            raise ValueError("Baseline changed")
        write_json(artifact.path / "corpus.json", summary)
        target = artifact.publish("frozen")
    write_json(
        ROOT / "docs/Q06_5E_CORPUS.json", {**summary, "artifact_directory": str(target)}
    )
    print(target)


def load_corpus():
    summary = json.loads((ROOT / "docs/Q06_5E_CORPUS.json").read_text())
    path = Path(summary["artifact_directory"]) / "documents.json"
    if sha256_file(path) != summary["documents_sha256"]:
        raise ValueError("Frozen corpus changed")
    data = json.loads(path.read_text())["documents"]
    for doc in data:
        if any(
            document_id((ROOT / source).read_bytes()) != doc["metadata"]["doc_id"]
            for source in doc["metadata"]["sources"]
        ):
            raise ValueError("Original PDF changed since corpus freeze")
    return data, summary


def encode_batches(encoder, texts, kind, batch_size):
    matrices, started = [], time.perf_counter()
    for start in range(0, len(texts), 64):
        matrix = encoder.encode(
            texts[start : start + 64],
            kind=kind,
            batch_size=batch_size,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        matrices.append(matrix)
        if str(encoder.model.device).startswith("mps"):
            import torch

            before_clear = torch.mps.driver_allocated_memory()
            torch.mps.empty_cache()
            after_clear = torch.mps.driver_allocated_memory()
            RESOURCE_COUNTERS["mps_driver_max_sampled_bytes"] = max(
                RESOURCE_COUNTERS["mps_driver_max_sampled_bytes"], before_clear
            )
            RESOURCE_COUNTERS["mps_driver_max_after_cache_clear_bytes"] = max(
                RESOURCE_COUNTERS["mps_driver_max_after_cache_clear_bytes"], after_clear
            )
            if after_clear > 6 * 1024**3:
                raise RuntimeError(
                    "MPS allocation remains above 6 GiB after cache release; rerun explicitly on CPU"
                )
        if start % 256 == 0 or start + 64 >= len(texts):
            print(
                f"{kind}: {min(start + 64, len(texts))}/{len(texts)}; {time.perf_counter() - started:.1f}s",
                flush=True,
            )
    return np.concatenate(matrices), time.perf_counter() - started


def evaluate(questions, documents, vectors, query_vectors):
    records = []
    for row, query in zip(questions, query_vectors, strict=True):
        if row["split"] != "dev":
            raise ValueError("Reserve queries are disabled")
        scores = cosine_scores(vectors, query)
        ranked = [
            {"document": documents[int(i)], "score": float(scores[i])}
            for i in top_indices(scores, 10)
        ]
        records.append(
            {
                "question_id": row["question_id"],
                "raw_metrics": retrieval_metrics(row, ranked),
                "raw_ranked": ranked,
            }
        )
    return {
        "summary": aggregate_metrics(records, "raw_metrics"),
        "records": records,
        "min_score": None,
        "reserve_queries_executed": 0,
        "generation_requests": 0,
    }


def selected_variant(results, variants):
    eligible = [v for v in variants if v["strategy"] != "legacy-frozen"]

    def key(v):
        r = results[v["name"]]
        at = r["summary"]["at_k"]
        return (
            at["10"]["complete_anchor_recall"],
            at["5"]["mean_anchor_character_coverage"],
            -r["chunk_count"],
        )

    chosen = max(eligible, key=key)
    selected = results[chosen["name"]]["summary"]["at_k"]["10"]
    baseline = results["minilm-old-chunks"]["summary"]["at_k"]["10"]
    if any(
        selected[k] < baseline[k]
        for k in ["complete_anchor_recall", "mean_anchor_character_coverage"]
    ):
        raise ValueError(
            "Pilot candidate did not meet baseline gate; do not build full index"
        )
    return chosen


def new_chunks(documents, encoder, variant):
    processor = ParagraphProcessor(
        encoder,
        target_tokens=variant["target_tokens"],
        overlap_tokens=variant["overlap_tokens"],
        use_blocks=variant["strategy"] == "page-block",
    )
    return unique_chunks(
        [chunk for doc in documents for chunk in processor.process_document(doc)]
    )


def init_encoder(device):
    import torch

    torch.set_num_threads(1)
    torch.manual_seed(0)
    profile, _ = profile_from_file(PROFILE)
    return CandidateEncoder(profile, device=device)


def pilot(device, batch_size):
    before = fingerprints()
    corpus, summary = load_corpus()
    _, _, dataset, _ = validate_dataset()
    questions = dataset["dev"]
    dev_ids = {a["doc_id"] for q in questions for a in q["evidence"]}
    reserve_ids = {a["doc_id"] for q in dataset["reserve"] for a in q["evidence"]}
    protocol = json.loads(PROTOCOL.read_text())
    distractors = sorted(
        d["metadata"]["doc_id"]
        for d in corpus
        if d["metadata"]["doc_id"] not in dev_ids | reserve_ids
    )[: protocol["pilot_additional_distractors"]]
    pilot_ids = dev_ids | set(distractors)
    corpus = [d for d in corpus if d["metadata"]["doc_id"] in pilot_ids]
    legacy = json.loads(BASELINES[0].read_text())
    indices = [i for i, d in enumerate(legacy["documents"]) if d["doc_id"] in pilot_ids]
    old_docs = [legacy["documents"][i] for i in indices]
    old_vectors = np.asarray([legacy["vectors"][i] for i in indices], dtype=np.float32)
    del legacy
    gc.collect()
    baseline = json.loads((ROOT / "docs/Q10A_BASELINE.json").read_text())
    query_file = Path(baseline["artifact_directory"]) / "query_vectors.npy"
    if (
        baseline["index_sha256"] != before["data/vector_db/vector_index.json"]
        or sha256_file(query_file) != baseline["query_vectors_sha256"]
        or baseline["question_ids"] != [q["question_id"] for q in questions]
        or baseline["dataset_manifest_sha256"]
        != sha256_file(ROOT / "evaluation/manifest.json")
    ):
        raise ValueError("Frozen MiniLM baseline or query order differs")
    old_queries = np.load(query_file, allow_pickle=False)
    encoder = init_encoder(device)
    query_vectors, query_seconds = encode_batches(
        encoder, [q["question"] for q in questions], "query", batch_size
    )
    results = {
        "minilm-old-chunks": {
            **evaluate(questions, old_docs, old_vectors, old_queries),
            "chunk_count": len(old_docs),
            "vectors_reused_from_q10a": True,
        }
    }
    with ArtifactRun("q065e_pilot") as artifact:
        np.save(artifact.path / "query_vectors.npy", query_vectors, allow_pickle=False)
        for variant in protocol["variants"]:
            name = variant["name"]
            print(name, flush=True)
            chunks = (
                old_docs
                if variant["strategy"] == "legacy-frozen"
                else new_chunks(corpus, encoder, variant)
            )
            vectors, seconds = encode_batches(
                encoder, [d["text"] for d in chunks], "document", batch_size
            )
            result = {
                **evaluate(questions, chunks, vectors, query_vectors),
                "chunk_count": len(chunks),
                "encoding_seconds": seconds,
                "max_input_tokens": max(encoder.count(d["text"]) for d in chunks),
            }
            write_json(artifact.path / f"{name}.json", result)
            results[name] = result
            del chunks, vectors
            gc.collect()
        chosen = selected_variant(results, protocol["variants"])
        report = {
            "schema": "chemqa-q065e-pilot-v1",
            "pilot_doc_ids": sorted(pilot_ids),
            "pilot_document_count": len(pilot_ids),
            "restricted_candidate_pool": True,
            "not_comparable_to_full_corpus_baseline": True,
            "annotation_quality": "AI draft; domain review pending",
            "profile": encoder.manifest(),
            "profile_sha256": sha256_file(PROFILE),
            "protocol_sha256": sha256_file(PROTOCOL),
            "corpus_sha256": summary["documents_sha256"],
            "selected_variant": chosen,
            "query_encoding_seconds": query_seconds,
            "actual_device": str(encoder.model.device),
            "actual_parameter_dtype": str(next(encoder.model.parameters()).dtype),
            "query_token_counts_including_prompt": [
                encoder.count(q["question"], "query") for q in questions
            ],
            "results": {
                k: {field: value for field, value in v.items() if field != "records"}
                for k, v in results.items()
            },
            "baseline_before": before,
            "baseline_after": fingerprints(),
            "reserve_queries_executed": 0,
            "generation_requests": 0,
        }
        write_json(
            artifact.path / "minilm-old-chunks.json", results["minilm-old-chunks"]
        )
        write_json(artifact.path / "pilot.json", report)
        if before != report["baseline_after"]:
            raise ValueError("Baseline changed")
        target = artifact.publish("passed_pilot", {"config": runtime_config(encoder)})
    write_json(
        ROOT / "docs/Q06_5E_PILOT.json", {**report, "artifact_directory": str(target)}
    )
    print(target)


def validate_candidate(index, processed, corpus, encoder):
    if index["embedding"] != encoder.manifest():
        raise ValueError("Embedding profile mismatch")
    report = validate_locations(index, processed)
    docs = index["documents"]
    vectors = np.asarray(index["vectors"], dtype=np.float32)
    if (
        vectors.shape != (len(docs), encoder.profile["dimension"])
        or not np.isfinite(vectors).all()
        or not np.allclose(np.linalg.norm(vectors, axis=1), 1, atol=1e-4)
    ):
        raise ValueError("Invalid vector dimensions/normalization")
    groups = {}
    for d, p in zip(docs, processed, strict=True):
        if (
            d != {"text": p["text"], **p["metadata"]}
            or d["embedding_token_count"] != encoder.count(d["text"])
            or d["embedding_token_count"] > d["embedding_token_limit"]
        ):
            raise ValueError("Processed metadata or token count mismatch")
        groups.setdefault(d["doc_id"], []).append(d)
    if set(groups) != {d["metadata"]["doc_id"] for d in corpus}:
        raise ValueError("Candidate changed the corpus identities")
    for doc in corpus:
        ranges = sorted(
            (
                page["char_start"] + span["char_start"],
                page["char_start"] + span["char_end"],
            )
            for d in groups[doc["metadata"]["doc_id"]]
            for span in d["source_spans"]
            for page in [doc["pages"][span["page_number"] - 1]]
        )
        cursor = 0
        for start, end in ranges:
            if doc["text"][cursor:start].strip():
                raise ValueError("Chunking dropped non-whitespace source characters")
            cursor = max(cursor, end)
        if doc["text"][cursor:].strip():
            raise ValueError("Chunking dropped end of document")
    report.update(
        over_limit_chunks=0,
        actual_encoder_token_ids_match_untruncated_inputs=True,
        unit_normalized_vectors=True,
        source_nonwhitespace_fully_covered=True,
        max_document_input_tokens=max(encoder.count(d["text"]) for d in docs),
        embedding=encoder.manifest(),
    )
    return report


def build(device, batch_size):
    before = fingerprints()
    corpus, summary = load_corpus()
    pilot_report = json.loads((ROOT / "docs/Q06_5E_PILOT.json").read_text())
    if (
        pilot_report["profile_sha256"] != sha256_file(PROFILE)
        or pilot_report["protocol_sha256"] != sha256_file(PROTOCOL)
        or pilot_report["corpus_sha256"] != summary["documents_sha256"]
    ):
        raise ValueError("Pilot profile/protocol/corpus changed")
    encoder = init_encoder(device)
    started = time.perf_counter()
    chunks = new_chunks(corpus, encoder, pilot_report["selected_variant"])
    _, _, dataset, source_validation = validate_dataset()
    with ArtifactRun("indexes") as artifact:
        vectors, encoding_seconds = encode_batches(
            encoder, [d["text"] for d in chunks], "document", batch_size
        )
        query_vectors, query_seconds = encode_batches(
            encoder, [q["question"] for q in dataset["dev"]], "query", batch_size
        )
        index = {
            "documents": chunks,
            "vectors": vectors,
            "embedding": encoder.manifest(),
            "chunking": pilot_report["selected_variant"],
            "corpus_sha256": summary["documents_sha256"],
        }
        processed = [
            {"text": d["text"], "metadata": {k: v for k, v in d.items() if k != "text"}}
            for d in chunks
        ]
        validation = validate_candidate(index, processed, corpus, encoder)
        full = evaluate(dataset["dev"], chunks, vectors, query_vectors)
        write_json(
            artifact.path / "vector_index.json", {**index, "vectors": vectors.tolist()}
        )
        write_json(artifact.path / "processed_chunks.json", processed)
        write_json(artifact.path / "retrieval.json", full)
        np.save(artifact.path / "query_vectors.npy", query_vectors, allow_pickle=False)
        baseline = json.loads((ROOT / "docs/Q10A_BASELINE.json").read_text())
        report = {
            "schema": "chemqa-q065e-full-v1",
            "profile_sha256": sha256_file(PROFILE),
            "protocol_sha256": sha256_file(PROTOCOL),
            "dataset_manifest_sha256": sha256_file(ROOT / "evaluation/manifest.json"),
            "source_code_sha256": {
                name: sha256_file(ROOT / name)
                for name in [
                    "scripts/validate_q065e.py",
                    "src/knowledge_base/embedding.py",
                    "src/knowledge_base/paragraph_processor.py",
                    "src/knowledge_base/vector_store.py",
                    "src/evaluation/metrics.py",
                ]
            },
            "embedding": encoder.manifest(),
            "chunking": pilot_report["selected_variant"],
            "corpus_sha256": summary["documents_sha256"],
            "full_corpus_documents": len(corpus),
            "chunks": len(chunks),
            "summary": full["summary"],
            "legacy_full_corpus_summary": baseline["summary"]["raw"],
            "source_validation": source_validation,
            "validation": validation,
            "timings_seconds": {
                "encoding": encoding_seconds,
                "query_encoding": query_seconds,
                "total_before_publication": time.perf_counter() - started,
            },
            "rss_high_water_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            "mps_cache_release_after_each_outer_batch": True,
            "mps_memory_samples": dict(RESOURCE_COUNTERS),
            "actual_device": str(encoder.model.device),
            "actual_parameter_dtype": str(next(encoder.model.parameters()).dtype),
            "batch_size": batch_size,
            "query_token_counts_including_prompt": [
                encoder.count(q["question"], "query") for q in dataset["dev"]
            ],
            "total_document_input_tokens": sum(
                encoder.count(d["text"]) for d in chunks
            ),
            "versions": {
                p: importlib.metadata.version(p)
                for p in [
                    "sentence-transformers",
                    "transformers",
                    "torch",
                    "numpy",
                    "pymupdf",
                ]
            },
            "baseline_before": before,
            "baseline_after": fingerprints(),
            "default_switched": False,
            "reserve_queries_executed": 0,
            "generation_requests": 0,
            "annotation_quality": "AI draft; domain review pending",
        }
        if before != report["baseline_after"]:
            raise ValueError("Baseline changed")
        write_json(artifact.path / "evaluation.json", report)
        target = artifact.publish(
            "ready",
            {
                "embedding": encoder.manifest(),
                "config": runtime_config(encoder),
                "chunking": pilot_report["selected_variant"],
                "validation": validation,
                "files": {
                    name: sha256_file(artifact.path / name)
                    for name in [
                        "vector_index.json",
                        "processed_chunks.json",
                        "query_vectors.npy",
                        "retrieval.json",
                        "evaluation.json",
                    ]
                },
                "corpus_sha256": summary["documents_sha256"],
            },
        )
    write_json(
        ROOT / "docs/Q06_5E_FULL.json",
        {
            **report,
            "artifact_directory": str(target),
            "vector_index_bytes": (target / "vector_index.json").stat().st_size,
        },
    )
    print(target)


def probe(device):
    import torch

    corpus, _ = load_corpus()
    pilot_report = json.loads((ROOT / "docs/Q06_5E_PILOT.json").read_text())
    pilot_ids = set(pilot_report["pilot_doc_ids"])
    encoder = init_encoder(device)
    chunks = new_chunks(
        [d for d in corpus if d["metadata"]["doc_id"] in pilot_ids],
        encoder,
        pilot_report["selected_variant"],
    )
    texts = sorted([d["text"] for d in chunks], key=encoder.count, reverse=True)[:64]
    encoder.encode(texts[:1], show_progress_bar=False)
    records, matrices = [], []
    for batch in [8, 16]:
        start = time.perf_counter()
        vectors = encoder.encode(texts, batch_size=batch, show_progress_bar=False)
        matrices.append(vectors)
        records.append(
            {
                "batch_size": batch,
                "seconds_for_64_long_inputs": time.perf_counter() - start,
                "rss_high_water_bytes": resource.getrusage(
                    resource.RUSAGE_SELF
                ).ru_maxrss,
                "mps_allocated_bytes": torch.mps.current_allocated_memory()
                if str(encoder.model.device).startswith("mps")
                else None,
                "mps_driver_allocated_bytes": torch.mps.driver_allocated_memory()
                if str(encoder.model.device).startswith("mps")
                else None,
            }
        )
    close = bool(np.allclose(matrices[0], matrices[1], atol=1e-3, rtol=1e-3))
    faster = (
        records[1]["seconds_for_64_long_inputs"]
        < records[0]["seconds_for_64_long_inputs"]
    )
    within_memory = (records[1]["mps_driver_allocated_bytes"] or 0) < 6 * 1024**3
    selected = 16 if close and faster and within_memory else 8
    report = {
        "schema": "chemqa-q065e-resource-v1",
        "actual_device": str(encoder.model.device),
        "dtype": str(next(encoder.model.parameters()).dtype),
        "sample_count": len(texts),
        "input_token_range": [
            min(map(encoder.count, texts)),
            max(map(encoder.count, texts)),
        ],
        "records": records,
        "batch_vectors_allclose_atol_rtol_1e3": close,
        "max_absolute_batch_difference": float(
            np.max(np.abs(matrices[0] - matrices[1]))
        ),
        "selected_batch_size": selected,
        "selection_rule": "16 only if faster, vectors allclose(1e-3), and driver allocation below 6 GiB; otherwise 8",
        "memory_note": "RSS is process high-water; MPS figures are sampled allocator values, not measured peaks. One local probe is not a speed benchmark.",
        "generation_requests": 0,
    }
    write_json(ROOT / "docs/Q06_5E_RESOURCE.json", report)
    print(json.dumps(report, indent=2))


def replay(candidate, device):
    from config.settings import configure_paths, settings
    from src.knowledge_base.vector_store import VectorStore

    before = fingerprints()
    candidate = Path(candidate).resolve()
    old = json.loads((candidate / "evaluation.json").read_text())
    manifest = json.loads((candidate / "run.json").read_text())
    for name, checksum in manifest["files"].items():
        if sha256_file(candidate / name) != checksum:
            raise ValueError("Published candidate file checksum mismatch")
    if old["profile_sha256"] != sha256_file(PROFILE) or old[
        "dataset_manifest_sha256"
    ] != sha256_file(ROOT / "evaluation/manifest.json"):
        raise ValueError("Candidate profile or evaluation dataset changed")
    settings.EMBEDDING_PROFILE = str(PROFILE)
    configure_paths(index_dir=candidate)
    store = VectorStore(device=device)
    _, _, dataset, _ = validate_dataset()
    stored_queries = np.load(candidate / "query_vectors.npy", allow_pickle=False)
    queries, seconds = encode_batches(
        store.encoder,
        [q["question"] for q in dataset["dev"]],
        "query",
        old["batch_size"],
    )
    saved_rankings = json.loads((candidate / "retrieval.json").read_text())
    reproduced = evaluate(
        dataset["dev"],
        store.vector_index["documents"],
        store.vector_index["vectors"],
        stored_queries,
    )
    reencoded = evaluate(
        dataset["dev"],
        store.vector_index["documents"],
        store.vector_index["vectors"],
        queries,
    )

    def ids(evaluation):
        return [
            [r["document"]["chunk_id"] for r in row["raw_ranked"]]
            for row in evaluation["records"]
        ]

    same_saved = (
        ids(reproduced) == ids(saved_rankings)
        and reproduced["summary"] == old["summary"]
    )
    same_encoded = (
        ids(reencoded) == ids(saved_rankings) and reencoded["summary"] == old["summary"]
    )
    close = bool(np.allclose(queries, stored_queries, atol=1e-3, rtol=1e-3))
    first_query = dataset["dev"][0]["question"]
    smoke = store.similarity_search(first_query, 10)
    smoke_ids = [r["document"]["chunk_id"] for r in smoke]
    report = {
        "schema": "chemqa-q065e-replay-v1",
        "passed": same_saved and same_encoded and close and before == fingerprints(),
        "artifact_directory": str(candidate),
        "checksums_verified": True,
        "query_vectors_allclose_atol_rtol_1e3": close,
        "query_vector_max_absolute_difference": float(
            np.max(np.abs(queries - stored_queries))
        ),
        "stored_query_rankings_and_metrics_equal": same_saved,
        "reencoded_query_rankings_and_metrics_equal": same_encoded,
        "public_vector_store_single_query_top10_equal": smoke_ids
        == ids(saved_rankings)[0],
        "query_encoding_seconds": seconds,
        "actual_device": str(store.model.device),
        "baseline_unchanged": before == fingerprints(),
        "generation_requests": 0,
        "reserve_queries_executed": 0,
    }
    write_json(ROOT / "docs/Q06_5E_REPLAY.json", report)
    if not report["passed"]:
        raise ValueError("Candidate replay verification failed")
    print(json.dumps(report, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["freeze", "pilot", "probe", "build", "replay"])
    parser.add_argument("--device", choices=["auto", "cpu", "mps"], default="auto")
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument(
        "--candidate", type=Path, help="Published candidate directory for replay"
    )
    args = parser.parse_args()
    if args.mode == "freeze":
        corpus_freeze()
    elif args.mode == "pilot":
        pilot(args.device, args.batch_size)
    elif args.mode == "probe":
        probe(args.device)
    elif args.mode == "build":
        build(args.device, args.batch_size)
    else:
        if args.candidate is None:
            parser.error("replay requires --candidate")
        replay(args.candidate, args.device)


if __name__ == "__main__":
    main()
