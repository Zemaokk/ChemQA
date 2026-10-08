"""Capture, restore and replay the offline pre-upgrade reference; never call an LLM."""

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import time
import zipfile
from datetime import UTC, datetime
from importlib.metadata import distributions
from pathlib import Path
from unittest.mock import patch

import numpy as np
import torch

from config.settings import BASE_DIR, settings
from src.knowledge_base.retriever import Retriever
from src.knowledge_base.similarity import cosine_scores, top_indices

ROOT = Path(BASE_DIR)
DATA_PATHS = (
    "data/vector_db/vector_index.json",
    "data/processed/processed_chunks.json",
)
QUERIES = (
    "mechanism of CO2 electroreduction on Cu single-atom catalysts",
    "electrochemical oxidation of alcohols to aldehydes",
    "electrochemical C-H functionalization of arenes",
    "electrochemical synthesis of heterocyclic compounds",
    "electrochemical reduction of carbonyl compounds",
    "醇电氧化为醛的电解液与反应条件是什么？",
    "What electrolyte and potential were used for carbonyl electroreduction?",
)


def digest(path):
    result = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def command(args, cwd=ROOT):
    started = time.perf_counter()
    result = subprocess.run(
        args, cwd=cwd, capture_output=True, text=True, timeout=240, check=False
    )
    return {
        "command": args,
        "exit_code": result.returncode,
        "seconds": time.perf_counter() - started,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def runtime():
    hardware = command(["/usr/sbin/system_profiler", "SPHardwareDataType", "-json"])
    try:
        values = json.loads(hardware["stdout"])["SPHardwareDataType"][0]
        hardware = {
            key: values.get(key)
            for key in (
                "machine_model",
                "chip_type",
                "physical_memory",
                "number_processors",
            )
        }
    except (ValueError, KeyError, IndexError):
        hardware = {"status": "unavailable", "exit_code": hardware["exit_code"]}
    cpu = torch.tensor([1.0, 2.0]) @ torch.tensor([3.0, 4.0])
    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "architecture": platform.machine(),
        "logical_cpus": os.cpu_count(),
        "hardware": hardware,
        "disk_free_bytes": shutil.disk_usage(ROOT).free,
        "cpu_tensor_smoke": float(cpu) == 11.0,
        "mps_built": torch.backends.mps.is_built(),
        "mps_available_in_this_process": torch.backends.mps.is_available(),
        "cuda_available": torch.cuda.is_available(),
        "packages": dict(
            sorted((d.metadata["Name"], d.version) for d in distributions())
        ),
    }


def safe_config():
    # Explicit allowlist: do not serialize settings wholesale or copy .env.
    return {
        "embedding_model": settings.EMBEDDING_MODEL,
        "embedding_revision": settings.EMBEDDING_MODEL_REVISION,
        "retrieval_top_k": settings.RETRIEVAL_TOP_K,
        "context_min_score": 0.5,
        "chunk_overlap_tokens": settings.CHUNK_OVERLAP_TOKENS,
        "max_output_tokens": settings.MAX_TOKENS,
        "api_model": settings.DEEPSEEK_API_CONFIG["model"],
        "api_base_url": settings.DEEPSEEK_API_CONFIG["base_url"],
        "api_temperature": settings.DEEPSEEK_API_CONFIG["temperature"],
        "api_key_configured": bool(settings.DEEPSEEK_API_CONFIG["api_key"]),
        "pdf_engine": settings.PDF_PARSING_ENGINE,
    }


def load_reference_model():
    # Pin replay to CPU and one Torch thread; record auto-selected device separately.
    torch.set_num_threads(1)
    retriever = Retriever()
    original_device = str(retriever.vector_store.model.device)
    retriever.vector_store.model.to("cpu")
    retriever.vector_store.model.eval()
    return retriever, original_device


def retrieval(retriever, queries):
    store = retriever.vector_store
    reports, embeddings = [], []
    for query in queries:
        started = time.perf_counter()
        with patch.object(store.model, "encode", wraps=store.model.encode) as encode:
            hits = retriever.search(query, top_k=settings.RETRIEVAL_TOP_K)
            if encode.call_count != 1 or encode.call_args.args != (query,):
                raise ValueError("Reference must encode only one query per search")
        # Capture the query vector independently to allow model-free replay too.
        vector = np.asarray(store.encode_texts(query))
        scores = cosine_scores(store.vector_index["vectors"], vector)
        selected = top_indices(scores, settings.RETRIEVAL_TOP_K)
        expected_ids = [
            store.vector_index["documents"][i]["chunk_id"] for i in selected
        ]
        if expected_ids != [hit["document"]["chunk_id"] for hit in hits]:
            raise ValueError("Repeated query encoding changed reference ranks")
        np.testing.assert_allclose(
            scores[selected], [hit["score"] for hit in hits], atol=1e-12, rtol=0
        )
        embeddings.append(vector)
        accepted = [hit["document"] for hit in hits if hit["score"] >= 0.5]
        from src.qa_system.context import serialize_context

        reports.append(
            {
                "query": query,
                "query_tokens": store.budget.count(query),
                "seconds_including_repeat_encoding": time.perf_counter() - started,
                "top_k": hits,
                "accepted_chunk_ids_at_0_5": [d["chunk_id"] for d in accepted],
                "serialized_context_sha256": hashlib.sha256(
                    serialize_context(accepted).encode()
                ).hexdigest(),
            }
        )
    return reports, np.stack(embeddings)


def capture(folder, report_path):
    folder.mkdir(parents=True, exist_ok=False)
    before = {name: digest(ROOT / name) for name in DATA_PATHS}
    config = safe_config()
    resources = runtime()
    retriever, device = load_reference_model()
    store = retriever.vector_store
    runs, embeddings = retrieval(retriever, QUERIES)
    for name in DATA_PATHS:
        target = folder / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, target)
    store.model.save(str(folder / "model"))
    np.save(folder / "query_vectors.npy", embeddings, allow_pickle=False)
    write_json(folder / "retrieval.json", runs)
    write_json(folder / "config.json", config)
    # Archive executable source and lockfiles, excluding secrets, PDFs and caches.
    sources = set(ROOT.glob("*.py"))
    for directory in ("config", "src", "scripts", "tests"):
        sources.update((ROOT / directory).rglob("*.py"))
    sources.update((ROOT / "tests/fixtures").glob("*.json"))
    sources.update(
        ROOT / name
        for name in (
            "pyproject.toml",
            "uv.lock",
            ".python-version",
            ".gitignore",
            "README.md",
        )
        if (ROOT / name).is_file()
    )
    with zipfile.ZipFile(folder / "source.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for source in sorted(sources):
            archive.write(source, source.relative_to(ROOT))
    validations = []
    for label, args in (
        (
            "unittest",
            [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
        ),
        ("ruff_check", [sys.executable, "-m", "ruff", "check", "."]),
        ("ruff_format", [sys.executable, "-m", "ruff", "format", "--check", "."]),
        (
            "q06",
            [
                sys.executable,
                "-m",
                "scripts.validate_q06",
                "--report",
                str(folder / "q06.json"),
            ],
        ),
    ):
        result = command(args)
        write_json(folder / f"{label}.log.json", result)
        validations.append({"name": label, "exit_code": result["exit_code"]})
        if result["exit_code"]:
            raise ValueError(f"{label} failed; inspect {folder}")
    after = {name: digest(ROOT / name) for name in DATA_PATHS}
    if before != after:
        raise ValueError("Capture modified active data")
    files = {
        str(path.relative_to(folder)): {
            "sha256": digest(path),
            "bytes": path.stat().st_size,
        }
        for path in sorted(folder.rglob("*"))
        if path.is_file()
    }
    manifest = {
        "schema": "chemqa-q065a-reference-v1",
        "created_utc": datetime.now(UTC).isoformat(),
        "git_head": command(["git", "rev-parse", "HEAD"])["stdout"].strip(),
        "git_status_at_capture": command(["git", "status", "--short"])["stdout"],
        "config": config,
        "resources": resources,
        "embedding_manifest": store.budget.manifest(),
        "index": {
            "documents": len(store.vector_index["documents"]),
            "unique_pdfs": len({d["doc_id"] for d in store.vector_index["documents"]}),
            "vector_shape": list(store.vector_index["vectors"].shape),
            "sha256": after,
        },
        "replay": {
            "device": "cpu",
            "auto_selected_device": device,
            "torch_threads": 1,
            "score_atol": 1e-12,
            "query_vector_atol": 1e-7,
        },
        "queries": [
            {
                "query": r["query"],
                "top_ids": [h["document"]["chunk_id"] for h in r["top_k"]],
                "accepted_count": len(r["accepted_chunk_ids_at_0_5"]),
            }
            for r in runs
        ],
        "validations": validations,
        "files": files,
        "active_data_unchanged": True,
        "external_api_requests": 0,
        "limitations": [
            "Execution reference only; questions have no relevance labels.",
            "No live LLM baseline or scientific-support evaluation.",
            "MPS availability describes this process, not all host environments.",
            "Raw PDFs are not copied; retrieval replay needs only captured index/model/source.",
            "Installed packages are inventoried; wheels and Python runtime are not archived.",
        ],
    }
    write_json(folder / "manifest.json", manifest)
    write_json(report_path, {"local_bundle": str(folder.relative_to(ROOT)), **manifest})
    print(f"Captured {len(runs)} queries and {len(files)} artifacts: {folder}")


def check_bundle(folder):
    manifest = json.loads((folder / "manifest.json").read_text())
    for name, value in manifest["files"].items():
        path = folder / name
        if digest(path) != value["sha256"]:
            raise ValueError(f"Reference artifact changed: {name}")
    return manifest


def verify(folder, report_path):
    manifest = check_bundle(folder)
    for name, expected in manifest["index"]["sha256"].items():
        if digest(ROOT / name) != expected:
            raise ValueError(f"Active data differs from reference: {name}")
    current_config = safe_config()
    expected_config = dict(manifest["config"])
    # Credential presence is informational; restoring credentials is deliberately excluded.
    current_config.pop("api_key_configured")
    expected_config.pop("api_key_configured")
    if current_config != expected_config:
        raise ValueError("Effective nonsecret config differs from reference")
    retriever, _ = load_reference_model()
    runs, vectors = retrieval(retriever, [r["query"] for r in manifest["queries"]])
    old_vectors = np.load(folder / "query_vectors.npy", allow_pickle=False)
    np.testing.assert_allclose(vectors, old_vectors, atol=1e-7, rtol=0)
    expected = json.loads((folder / "retrieval.json").read_text())
    for old, new in zip(expected, runs, strict=True):
        for key in (
            "query",
            "query_tokens",
            "accepted_chunk_ids_at_0_5",
            "serialized_context_sha256",
        ):
            if old[key] != new[key]:
                raise ValueError(f"Replay mismatch: {key}")
        if [h["document"] for h in old["top_k"]] != [
            h["document"] for h in new["top_k"]
        ]:
            raise ValueError("Replay evidence/ranks differ")
        np.testing.assert_allclose(
            [h["score"] for h in old["top_k"]],
            [h["score"] for h in new["top_k"]],
            atol=1e-12,
            rtol=0,
        )
    # Replay scores independently with the captured query vectors.
    for vector, run in zip(old_vectors, expected, strict=True):
        scores = cosine_scores(retriever.vector_store.vector_index["vectors"], vector)
        selected = top_indices(scores, manifest["config"]["retrieval_top_k"])
        ids = [
            retriever.vector_store.vector_index["documents"][i]["chunk_id"]
            for i in selected
        ]
        if ids != [h["document"]["chunk_id"] for h in run["top_k"]]:
            raise ValueError("Stored-query-vector replay differs")
    report = {
        "bundle_integrity": "passed",
        "reencoded_queries": len(runs),
        "ranks_evidence_scores_context_match": True,
        "stored_query_vector_replay": "passed",
        "external_api_requests": 0,
        "root": str(ROOT),
    }
    write_json(report_path, report)
    print(json.dumps(report, ensure_ascii=False))


def restore(folder, destination):
    manifest = check_bundle(folder)
    destination.mkdir(parents=True, exist_ok=False)
    with zipfile.ZipFile(folder / "source.zip") as archive:
        for name in archive.namelist():
            target = (destination / name).resolve()
            if not target.is_relative_to(destination):
                raise ValueError("Unsafe source archive path")
        archive.extractall(destination)
    for name in DATA_PATHS:
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(folder / name, target)
    model_name = Path(manifest["config"]["embedding_model"])
    if model_name.is_absolute() or ".." in model_name.parts:
        raise ValueError("Model identifier cannot form a local restore path")
    shutil.copytree(folder / "model", destination / "models" / model_name)
    # Restore nonsecret environment values only; users configure credentials separately.
    config = manifest["config"]
    environment = {
        "CHEMQA_EMBEDDING_MODEL": config["embedding_model"],
        "CHEMQA_EMBEDDING_REVISION": config["embedding_revision"] or "",
        "DEEPSEEK_MODEL": config["api_model"],
        "DEEPSEEK_BASE_URL": config["api_base_url"],
        "DEEPSEEK_TEMPERATURE": str(config["api_temperature"]),
    }
    (destination / ".env").write_text(
        "\n".join(f"{key}={value}" for key, value in environment.items()) + "\n"
    )
    print(f"Restored isolated reference to {destination}; no credentials copied")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("capture", "verify", "restore"))
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--destination", type=Path)
    args = parser.parse_args()
    bundle = args.bundle.resolve()
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["MPLBACKEND"] = "Agg"
    # Deny network even if future callers accidentally reach the requests API.
    with patch(
        "requests.sessions.Session.request",
        side_effect=RuntimeError("Q06.5-A is offline"),
    ):
        if args.action == "capture":
            if not args.report:
                parser.error("capture requires --report")
            capture(bundle, args.report)
        elif args.action == "verify":
            if not args.report:
                parser.error("verify requires --report")
            verify(bundle, args.report)
        else:
            if not args.destination:
                parser.error("restore requires --destination")
            restore(bundle, args.destination.resolve())


if __name__ == "__main__":
    main()
