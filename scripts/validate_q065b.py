"""Record bounded live generation using the frozen Q10-A development prompts only."""

import argparse
import hashlib
from pathlib import Path

from config.prompts import PROMPT_VERSION
from config.settings import BASE_DIR, resolve_path, settings
from src.api_integration.api_generator import DeepSeekAnswerGenerator
from src.api_integration.api_handler import DeepSeekAPIHandler
from src.evaluation.dataset import read_json, validate_dataset
from src.evaluation.metrics import manual_review_template
from src.utils.artifacts import ArtifactRun, sha256_file, write_json


def load_inputs(report_path):
    """Use actual retrieval snapshots, never gold answers or annotated source passages."""
    report = read_json(report_path)
    manifest, _, questions, validation = validate_dataset()
    if report["dataset_manifest_sha256"] != sha256_file(
        Path(BASE_DIR) / "evaluation/manifest.json"
    ):
        raise ValueError("Frozen question set differs from retrieval baseline")
    if report["index_sha256"] != sha256_file(
        Path(settings.VECTOR_DB_DIR) / "vector_index.json"
    ):
        raise ValueError("Active index differs from retrieval baseline")
    records = read_json(resolve_path(report["artifact_directory"]) / "retrieval.json")[
        "records"
    ]
    expected = questions["dev"]
    if [r["question_id"] for r in records] != [q["question_id"] for q in expected]:
        raise ValueError("Development question identity mismatch")
    generator = DeepSeekAnswerGenerator()
    inputs = []
    for row, question in zip(records, expected, strict=True):
        if (
            row["question"] != question["question"]
            or row["generation_input"]["prompt_version"] != PROMPT_VERSION
        ):
            raise ValueError("Question or prompt version changed")
        context = [
            hit["document"]
            for hit in row["raw_ranked"]
            if hit["document"]["chunk_id"] in row["context_chunk_ids"]
        ]
        prepared = generator._prepare(question["question"], context)
        if prepared.record() != {
            k: v for k, v in row["generation_input"].items() if k != "prompt_sent"
        }:
            raise ValueError("Prepared evidence or prompt differs from frozen snapshot")
        inputs.append((question, prepared))
    return report, manifest, validation, inputs


def prepare_baseline(report_path):
    report, manifest, validation, inputs = load_inputs(report_path)
    handler = DeepSeekAPIHandler()
    handler.config["max_attempts"] = 1
    profile = handler.request_parameters()
    with ArtifactRun("q065b_previews") as run:
        files, documents = {}, {}
        for question, prepared in inputs:
            name = question["question_id"] + ".json"
            write_json(
                run.path / name,
                {
                    "question_id": question["question_id"],
                    "generation_input": {**prepared.record(), "prompt_sent": False},
                },
            )
            files[name] = sha256_file(run.path / name)
            for chunk in prepared.chunks:
                documents[chunk["doc_id"]] = {
                    "source": chunk["source"],
                    "doc_id": chunk["doc_id"],
                }
        protocol = {
            "schema": "chemqa-q065b-preview-v1",
            "dataset_version": manifest["version"],
            "dataset_manifest_sha256": report["dataset_manifest_sha256"],
            "retrieval_report_sha256": sha256_file(report_path),
            "retrieval_records_sha256": sha256_file(
                resolve_path(report["artifact_directory"]) / "retrieval.json"
            ),
            "request_parameters": profile,
            "question_ids": [q["question_id"] for q, _ in inputs],
            "files_sha256": files,
            "documents": list(documents.values()),
            "generation_requests": 0,
            "reserve_queries_executed": 0,
            "source_validation": validation,
        }
        write_json(run.path / "protocol.json", protocol)
        target = run.publish("prepared", {"generation_requests": 0})
    return {**protocol, "artifact_directory": str(target)}


def verify_preview(preview_path, inputs, profile, report_path):
    protocol = read_json(preview_path / "protocol.json")
    if protocol["request_parameters"] != profile or protocol[
        "retrieval_report_sha256"
    ] != sha256_file(report_path):
        raise ValueError("Prepared configuration or retrieval baseline changed")
    expected = [q["question_id"] for q, _ in inputs]
    if protocol["question_ids"] != expected:
        raise ValueError("Prepared question scope changed")
    for question, prepared in inputs:
        name = question["question_id"] + ".json"
        path = preview_path / name
        if protocol["files_sha256"][name] != sha256_file(path):
            raise ValueError("Prepared file changed")
        if read_json(path) != {
            "question_id": question["question_id"],
            "generation_input": {**prepared.record(), "prompt_sent": False},
        }:
            raise ValueError("Prepared evidence or prompt changed")
    return sha256_file(preview_path / "protocol.json")


def baseline(report_path, preview_path):
    report, manifest, validation, inputs = load_inputs(report_path)
    generator = DeepSeekAnswerGenerator()
    # Baseline is one predeclared attempt per question, not a quality comparison.
    generator.api_handler.config["max_attempts"] = 1
    profile = generator.api_handler.request_parameters()
    preview_hash = verify_preview(preview_path, inputs, profile, report_path)
    rows = []
    with ArtifactRun("q065b_generation") as run:
        write_json(
            run.path / "protocol.json",
            {
                "dataset_version": manifest["version"],
                "dataset_manifest_sha256": report["dataset_manifest_sha256"],
                "retrieval_report_sha256": sha256_file(report_path),
                "preview_protocol_sha256": preview_hash,
                "runner_sha256": sha256_file(Path(__file__).resolve()),
                "index_sha256": report["index_sha256"],
                "request_parameters": profile,
                "question_ids": [q["question_id"] for q, _ in inputs],
                "repeats_per_question": 1,
                "reserve_queries_executed": 0,
                "quality_scores": None,
                "cost": None,
                "annotation_status": "AI draft; domain review pending",
            },
        )
        for question, prepared in inputs:
            result = generator.generate_answer_result(question["question"], prepared)
            record = {
                "question_id": question["question_id"],
                "generation_input": {
                    **prepared.record(),
                    "prompt_sent": result.request_sent,
                },
                "prompt_sha256": hashlib.sha256(prepared.text.encode()).hexdigest(),
                "result": result.record(),
                "answer": result.content,
                "quality_scores": None,
                "cost": None,
            }
            write_json(run.path / (question["question_id"] + ".json"), record)
            rows.append(
                {
                    k: v
                    for k, v in record.items()
                    if k not in {"generation_input", "answer"}
                }
            )
            write_json(run.path / "progress.json", {"results": rows})
            print(question["question_id"] + ": " + result.status, flush=True)
        empty = generator.generate_answer_result("No evidence control", [])
        if empty.request_sent or empty.status != "no_evidence":
            raise ValueError("Empty-evidence gate failed")
        summary = {
            "schema": "chemqa-q065b-generation-baseline-v1",
            "dataset_version": manifest["version"],
            "source_validation": validation,
            "request_parameters": profile,
            "execution_counts": {
                status: sum(r["result"]["status"] == status for r in rows)
                for status in ("success", "failed", "truncated", "no_evidence")
            },
            "generation_requests": sum(r["result"]["attempts"] for r in rows),
            "reserve_queries_executed": 0,
            "empty_evidence_control": empty.record(),
            "quality_scores": None,
            "cost": None,
            "results": rows,
        }
        write_json(run.path / "baseline.json", summary)
        write_json(
            run.path / "manual_review.json",
            manual_review_template([q for q, _ in inputs]),
        )
        target = run.publish(
            "recorded",
            {
                "generation_requests": summary["generation_requests"],
                "reserve_queries_executed": 0,
            },
        )
    return {**summary, "artifact_directory": str(target)}


def smoke():
    handler = DeepSeekAPIHandler()
    handler.config["max_attempts"] = 1
    rows = []
    with ArtifactRun("q065b_smoke") as run:
        for mode, budget in [("disabled", 512), ("enabled", 512), ("disabled", 1)]:
            handler.config["thinking"] = mode
            old_budget = settings.MAX_TOKENS
            settings.MAX_TOKENS = budget
            try:
                result = handler.generate_result(
                    "A box has 17 red and 23 blue balls. Remove 5 red balls, then double the remaining red balls. How many balls are there now? Give the final number only."
                )
            finally:
                settings.MAX_TOKENS = old_budget
            rows.append(
                {
                    "thinking": mode,
                    "max_tokens": budget,
                    "result": result.record(),
                    "answer": result.content,
                }
            )
            print(f"Smoke {mode}/{budget}: {result.status}", flush=True)
        generator = DeepSeekAnswerGenerator()
        empty = generator.generate_answer_result("No evidence control", [])
        passed = (
            rows[0]["result"]["status"] == "success"
            and not rows[0]["result"]["reasoning_content_present"]
            and rows[1]["result"]["status"] == "success"
            and rows[1]["result"]["reasoning_content_present"]
            and rows[2]["result"]["status"] == "truncated"
            and empty.status == "no_evidence"
            and not empty.request_sent
        )
        report = {
            "schema": "chemqa-q065b-live-smoke-v1",
            "passed": passed,
            "results": rows,
            "empty_evidence_control": empty.record(),
            "generation_requests": sum(r["result"]["attempts"] for r in rows),
            "cost": None,
        }
        write_json(run.path / "smoke.json", report)
        target = run.publish("passed" if passed else "failed")
    return {**report, "artifact_directory": str(target)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--live",
        action="store_true",
        help="Explicitly send potentially billable requests to the configured provider",
    )
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="Three bounded mode/truncation probes; otherwise run 20 development questions",
    )
    parser.add_argument(
        "--retrieval-report",
        type=Path,
        default=Path(BASE_DIR) / "docs/Q10A_BASELINE.json",
    )
    parser.add_argument("--report", type=Path)
    parser.add_argument(
        "--prepare",
        action="store_true",
        help="Prepare all outbound inputs locally without any provider call",
    )
    parser.add_argument(
        "--prepared-input",
        type=Path,
        help="Reviewed preview artifact; exact inputs are checked before sending",
    )
    args = parser.parse_args()
    if args.prepare:
        if args.live or args.smoke:
            parser.error("--prepare cannot send live requests")
        result = prepare_baseline(resolve_path(args.retrieval_report))
    else:
        if not args.live:
            parser.error(
                "Live requests require --live; use --prepare for a local preview"
            )
        if not args.smoke and not args.prepared_input:
            parser.error("Live baseline requires --prepared-input")
        result = (
            smoke()
            if args.smoke
            else baseline(
                resolve_path(args.retrieval_report), resolve_path(args.prepared_input)
            )
        )
    if args.report:
        write_json(resolve_path(args.report), result)
    print("Recorded run: " + result["artifact_directory"])


if __name__ == "__main__":
    main()
