"""Exercise real PDF/embedding candidate publication and isolated offline QA runs."""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pymupdf

from config.settings import BASE_DIR, configure_paths, settings
from scripts.validate_q07 import completion
from src.api_integration.result import APIGenerationError
from src.pipeline.vector_index_builder import VectorIndexBuilder
from src.qa_system.expert_system import ChemicalQAExpert
from src.utils.artifacts import create_session, finish_session, sha256_file, write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    active = [
        Path(settings.VECTOR_DB_DIR) / "vector_index.json",
        Path(settings.PROCESSED_DIR) / "processed_chunks.json",
    ]
    before = {str(path): sha256_file(path) for path in active}
    root = create_session("q08_validation")
    pdf_dir = root / "pdfs"
    pdf_dir.mkdir()
    query = "Electrochemical oxidation of alcohols produces aldehydes."
    with pymupdf.open() as pdf:
        pdf.new_page().insert_text((72, 72), query)
        pdf.new_page().insert_text(
            (72, 72), "This is a synthetic fixture for pipeline validation only."
        )
        pdf.save(pdf_dir / "synthetic.pdf")
    builder = VectorIndexBuilder(str(pdf_dir))
    candidate = builder.run_pipeline(destination=root / "candidate")
    manifest = json.loads((candidate / "run.json").read_text())
    if manifest["status"] != "ready":
        raise ValueError("Candidate was not validated")
    cases = []
    with (
        patch.object(settings, "VECTOR_DB_DIR", settings.VECTOR_DB_DIR),
        patch.object(settings, "PROCESSED_DIR", settings.PROCESSED_DIR),
        patch.object(settings, "OUTPUT_DIR", settings.OUTPUT_DIR),
    ):
        configure_paths(index_dir=candidate, output_dir=root / "runs")
        expert = ChemicalQAExpert()
        context = expert.retriever.retrieve_relevant_context(
            query, return_dict_list=True
        )
        if not context:
            raise ValueError("Real candidate retrieval returned no evidence")
        expert.generator.api_handler.config["api_key"] = "offline-fixture-only"
        text = f"Synthetic plumbing response [Ref {context[0]['chunk_id']}]"
        prior_answers = {}
        for label, response, expected in [
            ("first", completion(text), "success"),
            ("repeat", completion(text), "success"),
            ("failure", completion(None, status=401), "failed"),
        ]:
            with patch(
                "src.api_integration.api_handler.requests.post", return_value=response
            ) as post:
                try:
                    expert.answer_query(query, analyze_citations=True)
                except APIGenerationError as exc:
                    if expected != "failed" or exc.result.status != "failed":
                        raise
                if post.call_count != 1:
                    raise ValueError("Unexpected offline HTTP attempt count")
            target = expert.last_run_dir
            run_record = json.loads((target / "run.json").read_text())
            if (
                run_record["status"] != expected
                or run_record["index_sha256"] != manifest["files"]["vector_index.json"]
            ):
                raise ValueError("Run provenance or status differs")
            if expected == "failed":
                if (target / "answer.md").exists() or not (
                    target / "failure.json"
                ).is_file():
                    raise ValueError("Failure was saved as an answer")
            else:
                if not (target / "citation_analysis.txt").is_file():
                    raise ValueError("Requested citation report is missing")
                prior_answers[target / "answer.md"] = sha256_file(target / "answer.md")
            cases.append({"case": label, "status": expected, "directory": str(target)})
        if len({case["directory"] for case in cases}) != 3:
            raise ValueError("Repeated question overwrote an earlier run")
        if any(sha256_file(path) != digest for path, digest in prior_answers.items()):
            raise ValueError("Prior answer was modified")

    # Run the real entry point from outside the repository, with generation disabled
    # by an explicitly empty key. A non-empty retrieved context must fail clearly.
    env = {
        **os.environ,
        "PYTHONPATH": BASE_DIR,
        "HF_HUB_OFFLINE": "1",
        "DEEPSEEK_API_KEY": "",
    }
    outside_output = root / "outside-cli"
    command = [
        sys.executable,
        str(Path(BASE_DIR) / "main.py"),
        "-q",
        query,
        "--index-dir",
        str(candidate),
        "--output-dir",
        str(outside_output),
    ]
    process = subprocess.run(
        command,
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    runs = list(outside_output.glob("qa/*/run.json"))
    if process.returncode != 1 or len(runs) != 1:
        raise ValueError("Outside-root CLI did not save a configuration failure")
    failure = json.loads((runs[0].parent / "failure.json").read_text())
    if (
        failure["generation_result"]["error_code"] != "configuration"
        or failure["generation_result"]["request_sent"]
    ):
        raise ValueError("Empty-key CLI attempted generation")
    for module in (
        "src.pipeline.vector_index_builder",
        "qa_testing.direct_api_test",
        "qa_testing.test_organic_electrocatalysis_qa",
        "heatmap_visualization.run_heatmap",
    ):
        help_result = subprocess.run(
            [sys.executable, "-m", module, "--help"],
            cwd=root,
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if help_result.returncode:
            raise ValueError(f"Outside-root help failed: {module}")
    after = {str(path): sha256_file(path) for path in active}
    if before != after:
        raise ValueError("Active index or processed data changed")
    report = {
        "schema": "chemqa-q08-validation-v1",
        "status": "passed",
        "artifact_root": str(root),
        "candidate": str(candidate),
        "candidate_validation": manifest["validation"],
        "cases": cases,
        "outside_root_cli": {
            "exit_code": process.returncode,
            "status": "failed",
            "error_code": "configuration",
            "request_sent": False,
            "help_entry_points": 4,
        },
        "active_files_unchanged": before == after,
        "active_files_sha256": after,
        "live_api_calls": 0,
        "scope": "Synthetic two-page PDF; real local embedding and retrieval; mocked generation. No quality evaluation or full-corpus rebuild.",
    }
    finish_session(root, {"qa_cases": len(cases), "outside_root_cli": 1})
    write_json(args.report, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
