"""Exercise API result states with real retrieved evidence and mocked HTTP only."""

import argparse
import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import requests

from config.settings import settings
from scripts.validate_q065a import digest, write_json
from src.api_integration.result import APIGenerationError
from src.qa_system.expert_system import ChemicalQAExpert


def completion(content, *, reason="stop", status=200):
    response = Mock(status_code=status)
    response.json.return_value = {
        "id": "q07-offline-fixture",
        "model": "mock-model-not-a-live-result",
        "choices": [{"message": {"content": content}, "finish_reason": reason}],
        "usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120},
    }
    return response


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    files = [
        Path(settings.VECTOR_DB_DIR) / "vector_index.json",
        Path(settings.PROCESSED_DIR) / "processed_chunks.json",
    ]
    before = {p.name: digest(p) for p in files}
    expert = ChemicalQAExpert()
    question = "electrochemical oxidation of alcohols to aldehydes"
    context = expert.retriever.retrieve_relevant_context(
        question, return_dict_list=True
    )
    if not context:
        raise ValueError("Real retrieval returned no evidence")
    expert.generator.api_handler.config["api_key"] = "offline-fixture-only"
    text = f"Synthetic response for plumbing validation [Ref {context[0]['chunk_id']}]"
    scenarios = [
        ("success", [completion(text)], "success", context),
        ("authentication", [completion(None, status=401)], "failed", context),
        ("truncated", [completion(text, reason="length")], "truncated", context),
        (
            "timeout_exhausted",
            [requests.Timeout("offline fixture")] * 3,
            "failed",
            context,
        ),
        (
            "rate_limit_recovered",
            [completion(None, status=429), completion(text)],
            "success",
            context,
        ),
        ("server_exhausted", [completion(None, status=503)] * 3, "failed", context),
        ("empty_completion", [completion("")], "failed", context),
        ("no_evidence", [], "no_evidence", []),
    ]
    runs = []
    with tempfile.TemporaryDirectory(prefix="chemqa-q07-") as temporary:
        root = Path(temporary)
        (root / "answer_6.md").write_text("Legacy answer sentinel", encoding="utf-8")
        for name, responses, expected, evidence in scenarios:
            answer_path = root / "answer_6.md"
            prior_answer = answer_path.read_bytes() if answer_path.exists() else None
            with (
                patch("src.utils.artifacts.settings.OUTPUT_DIR", str(root)),
                patch.object(
                    expert.retriever, "retrieve_relevant_context", return_value=evidence
                ),
                patch(
                    "src.api_integration.api_handler.requests.post",
                    side_effect=responses,
                ) as post,
                patch("src.api_integration.api_handler.time.sleep"),
            ):
                try:
                    expert.answer_query(question, analyze_citations=False)
                except APIGenerationError as exc:
                    if exc.result.completed:
                        raise
                filename = (
                    "answer.evidence.json"
                    if expected in ("success", "no_evidence")
                    else "failure.json"
                )
                saved = json.loads((expert.last_run_dir / filename).read_text())
                result = saved["generation_result"]
                if (
                    result["status"] != expected
                    or result["attempts"] != post.call_count
                ):
                    raise ValueError(
                        "Saved result state disagrees with mocked HTTP attempts"
                    )
                if saved["generation_input"]["prompt_sent"] != bool(post.call_count):
                    raise ValueError("Prompt attempt recording disagrees")
                if saved["generation_input"]["decision"]["scientific_support_verified"]:
                    raise ValueError(
                        "Execution success was mislabeled as scientific support"
                    )
                if not expected in ("success", "no_evidence"):
                    if (
                        saved["raw_answer"] is not None
                        or answer_path.read_bytes() != prior_answer
                    ):
                        raise ValueError(
                            "Failure became an answer or overwrote prior success"
                        )
                elif expected == "success" and (
                    not saved["evidence_map"] or saved["unresolved_citations"]
                ):
                    raise ValueError("Canonical citation mapping failed")
                for call in post.call_args_list:
                    if (
                        call.kwargs["json"]["messages"][0]["content"]
                        != saved["generation_input"]["prompt"]
                    ):
                        raise ValueError(
                            "Sent prompt differs from saved evidence snapshot"
                        )
                runs.append(
                    {
                        "case": name,
                        "status": expected,
                        "generation_result": result,
                        "mocked_http_requests": post.call_count,
                        "failure_excluded_from_answer": expected
                        not in ("success", "no_evidence"),
                    }
                )
    after = {p.name: digest(p) for p in files}
    if before != after:
        raise ValueError("Validation changed active data")
    report = {
        "schema": "chemqa-q07-validation-v1",
        "real_retrieved_chunk_ids": [d["chunk_id"] for d in context],
        "synthetic_api_responses": True,
        "external_api_requests": 0,
        "runs": runs,
        "data_files_unchanged": True,
        "sha256": after,
        "limitation": "API execution states and citation plumbing only; no live model or scientific-support evaluation.",
    }
    write_json(args.report, report)
    print(
        f"Q07: {len(runs)} offline scenarios passed; real retrieval used {len(context)} chunks"
    )


if __name__ == "__main__":
    main()
