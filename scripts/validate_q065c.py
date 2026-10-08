"""Offline compatibility probes; synthetic inputs only, no index rebuild or API calls."""

import argparse
import gc
import importlib.metadata
import json
import platform
import resource
import time
from pathlib import Path

import numpy as np

from config.settings import BASE_DIR
from src.knowledge_base.similarity import cosine_scores, top_indices
from src.utils.artifacts import ArtifactRun, write_json


def select_device(requested, mps_available):
    if requested not in {"auto", "cpu", "mps"}:
        raise ValueError("Unknown device")
    if requested == "cpu":
        return "cpu", None
    if mps_available:
        return "mps", None
    return "cpu", "mps_unavailable"


def checked_token_counts(tokenizer, texts, limit):
    counts = [
        len(tokenizer(text, add_special_tokens=True, truncation=False)["input_ids"])
        for text in texts
    ]
    if any(n > limit for n in counts):
        raise ValueError("Probe input exceeds its explicit budget")
    return counts


def cpu_fallback(operation, device):
    try:
        return operation(device), None
    except (RuntimeError, NotImplementedError) as exc:
        if device == "cpu":
            raise
        # The callback must move/reload its model on the requested device.
        return operation("cpu"), type(exc).__name__


def legacy_compatibility():
    import torch

    from src.knowledge_base.vector_store import VectorStore

    torch.set_num_threads(1)
    report = json.loads((Path(BASE_DIR) / "docs/Q10A_BASELINE.json").read_text())
    records = json.loads(
        (Path(report["artifact_directory"]) / "retrieval.json").read_text()
    )["records"]
    old = np.load(
        Path(report["artifact_directory"]) / "query_vectors.npy", allow_pickle=False
    )
    store = VectorStore()
    store.model.to("cpu")
    queries = [r["question"] for r in records]
    current = store.encode_texts(
        queries, batch_size=8, show_progress_bar=False, convert_to_numpy=True
    )
    same_rankings = all(
        np.array_equal(
            top_indices(cosine_scores(store.vector_index["vectors"], a), 10),
            top_indices(cosine_scores(store.vector_index["vectors"], b), 10),
        )
        for a, b in zip(old, current, strict=True)
    )
    close = bool(np.allclose(old, current, atol=1e-5, rtol=1e-5))
    result = {
        "schema": "chemqa-q065c-legacy-compatibility-v1",
        "passed": close and same_rankings,
        "query_count": len(queries),
        "embedding_max_absolute_difference": float(np.max(np.abs(old - current))),
        "embeddings_allclose_atol_rtol_1e5": close,
        "all_top10_rankings_equal": same_rankings,
        "embedding_manifest": store.budget.manifest(),
        "index_sha256": store.index_sha256,
        "generation_requests": 0,
    }
    with ArtifactRun("q065c_legacy") as run:
        np.save(run.path / "query_vectors.npy", current, allow_pickle=False)
        write_json(run.path / "compatibility.json", result)
        target = run.publish("passed" if result["passed"] else "failed")
    return {**result, "artifact_directory": str(target)}


def model_probe(kind, spec, requested):
    import torch
    from sentence_transformers import CrossEncoder, SentenceTransformer

    start = time.perf_counter()
    cls = SentenceTransformer if kind == "embedding" else CrossEncoder
    model = cls(
        spec["model"],
        revision=spec["revision"],
        device="cpu",
        local_files_only=True,
        trust_remote_code=False,
        model_kwargs={"dtype": torch.float32, "attn_implementation": "sdpa"},
    )
    load_seconds = time.perf_counter() - start
    original_limit = int(model.max_seq_length)
    model.max_seq_length = 512
    query = "乙醇氧化为醛时生成什么产物？"
    documents = [
        "Oxidation of ethanol to an aldehyde produces acetaldehyde.",
        "Sodium chloride crystals have a cubic structure.",
    ]
    if kind == "embedding":
        rendered = [model.prompts["query"] + query, *documents]
    else:
        features = model.preprocess(inputs=[(query, d) for d in documents])
        rendered = [
            model.tokenizer.apply_chat_template(
                [
                    {"role": "query", "content": query},
                    {"role": "document", "content": doc},
                ],
                tokenize=False,
                add_generation_prompt=False,
            )
            for doc in documents
        ]
        if not all(
            query in text and doc in text
            for text, doc in zip(rendered, documents, strict=True)
        ):
            raise ValueError("Reranker template omitted a query or document")
    counts = checked_token_counts(model.tokenizer, rendered, 512)
    if kind == "reranker" and counts != [
        int(x) for x in features["attention_mask"].sum(dim=1)
    ]:
        raise ValueError("Reranker input was truncated or template differs")
    if any(n > 512 for n in counts):
        raise ValueError("Full reranker template exceeds probe budget")

    def compute(device, dtype=torch.float32, batch_size=2):
        model.to(device=device, dtype=dtype)
        if device == "mps":
            torch.mps.synchronize()
        began = time.perf_counter()
        if kind == "embedding":
            q = model.encode(
                [query],
                prompt_name="query",
                normalize_embeddings=True,
                show_progress_bar=False,
                convert_to_numpy=True,
            )
            docs = model.encode(
                documents,
                prompt_name="document",
                normalize_embeddings=True,
                batch_size=batch_size,
                show_progress_bar=False,
                convert_to_numpy=True,
            )
            values = np.concatenate([q, docs]).astype(np.float32)
        else:
            values = np.asarray(
                model.predict(
                    [(query, d) for d in documents],
                    batch_size=batch_size,
                    show_progress_bar=False,
                ),
                dtype=np.float32,
            ).reshape(-1)
        if device == "mps":
            torch.mps.synchronize()
        if not np.isfinite(values).all():
            raise RuntimeError("Nonfinite output")
        return values, time.perf_counter() - began

    cpu, cpu_seconds = compute("cpu")
    batch_one, _ = compute("cpu", batch_size=1)
    batch_error = float(np.max(np.abs(cpu - batch_one)))
    device, fallback_reason = select_device(
        requested, torch.backends.mps.is_available()
    )
    trials = []
    if device == "mps":
        for dtype in (torch.float32, torch.float16):
            (values, seconds), runtime_fallback = cpu_fallback(
                lambda d, dtype=dtype: compute(
                    d, dtype if d == "mps" else torch.float32
                ),
                device,
            )
            error = float(np.max(np.abs(cpu - values)))
            trials.append(
                {
                    "requested_device": "mps",
                    "actual_device": "cpu" if runtime_fallback else "mps",
                    "dtype": str(torch.float32 if runtime_fallback else dtype),
                    "requested_dtype": str(dtype),
                    "elapsed_seconds": seconds,
                    "max_abs_difference_from_cpu_fp32": error,
                    "fallback_reason": runtime_fallback,
                    "all_finite": True,
                    "mps_allocated_bytes": torch.mps.current_allocated_memory(),
                    "mps_driver_allocated_bytes": torch.mps.driver_allocated_memory(),
                }
            )
    scores = (cpu[0] @ cpu[1:].T).tolist() if kind == "embedding" else cpu.tolist()
    result = {
        "model": spec["model"],
        "revision": spec["revision"],
        "kind": kind,
        "load_seconds": load_seconds,
        "model_max_sequence_tokens": original_limit,
        "probe_sequence_limit": 512,
        "full_input_token_counts": counts,
        "output_shape": list(cpu.shape),
        "cpu_dtype": "float32",
        "cpu_batch_sizes_checked": [1, 2],
        "cpu_elapsed_seconds_batch2": cpu_seconds,
        "cpu_batch_max_absolute_difference": batch_error,
        "cpu_output": cpu.tolist() if kind == "reranker" else None,
        "synthetic_relevance_scores": scores,
        "synthetic_related_scores_higher": bool(scores[0] > scores[1]),
        "cpu_batch_consistent": bool(np.allclose(cpu, batch_one, atol=1e-4, rtol=1e-4)),
        "selected_device": device,
        "device_selection_fallback": fallback_reason,
        "accelerator_trials": trials,
        "rss_high_water_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "modules": [type(m).__name__ for m in model.children()],
        "generation_requests": 0,
    }
    result["passed"] = (
        result["cpu_batch_consistent"]
        and result["synthetic_related_scores_higher"]
        and all(
            t["max_abs_difference_from_cpu_fp32"]
            < (0.1 if kind == "reranker" else 0.01)
            for t in trials
        )
    )
    model = None
    gc.collect()
    if torch.backends.mps.is_available():
        torch.mps.empty_cache()
    return result


def main():
    import torch

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--models-manifest",
        type=Path,
        default=Path(BASE_DIR) / "config/model_candidates.json",
    )
    parser.add_argument("--device", choices=["auto", "cpu", "mps"], default="auto")
    parser.add_argument("--legacy", action="store_true")
    parser.add_argument(
        "--download",
        action="store_true",
        help="Download only the pinned public model assets; no inference or uploads",
    )
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    torch.set_num_threads(1)
    torch.manual_seed(0)
    if args.download:
        from huggingface_hub import snapshot_download

        specs = json.loads(args.models_manifest.read_text())
        rows = []
        for spec in specs:
            path = snapshot_download(
                spec["model"],
                revision=spec["revision"],
                token=False,
                allow_patterns=[
                    "*.json",
                    "*.safetensors",
                    "*.txt",
                    "*.jinja",
                    "README.md",
                ],
                max_workers=3,
            )
            rows.append(
                {
                    **spec,
                    "snapshot_path": path,
                    "downloaded_bytes": sum(
                        p.stat().st_size for p in Path(path).rglob("*") if p.is_file()
                    ),
                }
            )
        result = {"passed": True, "downloaded_models": rows, "generation_requests": 0}
    elif args.legacy:
        result = legacy_compatibility()
    else:
        specs = json.loads(args.models_manifest.read_text())
        rows = [
            model_probe(kind, spec, args.device)
            for kind, spec in zip(("embedding", "reranker"), specs, strict=True)
        ]
        result = {
            "schema": "chemqa-q065c-runtime-v1",
            "passed": all(r["passed"] for r in rows),
            "versions": {
                n: importlib.metadata.version(n)
                for n in [
                    "sentence-transformers",
                    "transformers",
                    "torch",
                    "huggingface-hub",
                    "httpx",
                    "socksio",
                    "numpy",
                ]
            },
            "platform": platform.platform(),
            "machine": platform.machine(),
            "mps_built": torch.backends.mps.is_built(),
            "mps_available": torch.backends.mps.is_available(),
            "torch_threads": 1,
            "models": rows,
            "generation_requests": 0,
            "quality_benchmark": False,
        }
        with ArtifactRun("q065c_runtime") as run:
            write_json(run.path / "runtime.json", result)
            target = run.publish("passed" if result["passed"] else "failed")
        result["artifact_directory"] = str(target)
    write_json(args.report, result)
    print("Q06.5-C passed:", result["passed"], flush=True)
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
