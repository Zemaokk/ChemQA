"""Controlled offline boundary fixtures; does not measure a live model's abstention."""

import argparse
import hashlib
import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

from config.settings import BASE_DIR, settings
from src.api_integration.api_generator import DeepSeekAnswerGenerator
from src.knowledge_base.identity import document_id, normalize_chunk
from src.qa_system.evidence_policy import NO_EVIDENCE_ANSWER
from src.qa_system.expert_system import ChemicalQAExpert
from src.qa_system.response_formatter import ResponseFormatter


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    fixture_path = Path(BASE_DIR) / "tests/fixtures/q06_boundary_cases.json"
    fixtures = json.loads(fixture_path.read_text())
    paths = [
        Path(settings.VECTOR_DB_DIR) / "vector_index.json",
        Path(settings.PROCESSED_DIR) / "processed_chunks.json",
    ]
    before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    generator = DeepSeekAnswerGenerator()
    generator.api_handler.config = {
        **generator.api_handler.config,
        "api_key": "offline-fixture-only",
    }
    generator.api_handler.headers = {"Content-Type": "application/json"}
    prompts = []

    def offline_response(*args, **kwargs):
        prompt = kwargs["json"]["messages"][0]["content"]
        data, _ = json.JSONDecoder().raw_decode(
            prompt.split("检索证据（JSON）：\n", 1)[1]
        )
        if not data["evidence"]:
            raise ValueError("Empty evidence reached HTTP instead of local handling")
        prompts.append(prompt)
        response = Mock(status_code=200)
        response.json.return_value = {
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {
                        "content": f"离线模拟响应；这不是模型的证据适用性判断。{data['evidence'][0]['citation']}"
                    },
                }
            ]
        }
        return response

    runs = []
    with (
        tempfile.TemporaryDirectory(prefix="chemqa-q06-") as folder,
        patch(
            "src.api_integration.api_handler.requests.post",
            side_effect=offline_response,
        ) as post,
        patch("src.utils.artifacts.settings.OUTPUT_DIR", folder),
    ):
        for case in fixtures["cases"]:
            chunks = [
                normalize_chunk(
                    {
                        "source": f"synthetic-{case['id']}.pdf",
                        "doc_id": document_id(case["id"].encode()),
                        "chunk_index": i,
                        "text": text,
                    }
                )
                for i, text in enumerate(case["texts"])
            ]
            expert = ChemicalQAExpert.__new__(ChemicalQAExpert)
            expert.retriever = Mock()
            expert.retriever.retrieve_relevant_context.return_value = chunks
            expert.generator = generator
            expert.formatter = ResponseFormatter()
            calls_before = post.call_count
            expert.answer_query(case["question"], analyze_citations=False)
            saved = json.loads(
                (expert.last_run_dir / "answer.evidence.json").read_text()
            )
            generation = saved["generation_input"]
            calls = post.call_count - calls_before
            if bool(calls) != bool(chunks) or generation["prompt_sent"] != bool(chunks):
                raise ValueError("Evidence gate and recorded request route disagree")
            if generation["decision"]["scientific_support_verified"]:
                raise ValueError(
                    "Candidate evidence was mislabeled as verified support"
                )
            if chunks:
                if generation["prompt"] != prompts[-1]:
                    raise ValueError("Actual prompt and saved prompt differ")
                for rule in (
                    "直接支持",
                    "部分支持",
                    "当前证据不足",
                    "不得外推成目标体系",
                    "待验证假设",
                ):
                    if rule not in prompts[-1]:
                        raise ValueError(
                            "Boundary instructions did not reach the API payload"
                        )
            elif (
                saved["raw_answer"] != NO_EVIDENCE_ANSWER
                or saved["evidence_map"]
                or saved["unresolved_citations"]
            ):
                raise ValueError(
                    "Empty-evidence output or citation record is inconsistent"
                )
            runs.append(
                {
                    "case": case["id"],
                    "expected_boundary_annotation": case["expected_boundary"],
                    "expected_boundary_reason": case["reason"],
                    "evidence_count": len(chunks),
                    "mocked_http_requests": calls,
                    "prompt_sent": generation["prompt_sent"],
                    "prompt_version": generation["prompt_version"],
                    "decision": generation["decision"],
                    "deterministic_empty_gate_verified": True if not chunks else None,
                    "nonempty_model_semantics_evaluated": False,
                }
            )
    after = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    if before != after:
        raise ValueError("Boundary validation modified indexed data")
    report = {
        "fixture_version": fixtures["fixture_version"],
        "fixture_sha256": hashlib.sha256(fixture_path.read_bytes()).hexdigest(),
        "synthetic": True,
        "runs": runs,
        "external_api_requests": 0,
        "data_files_unchanged": True,
        "sha256": after,
        "limitation": "Nonempty cases verify prompt delivery and unverified-support recording only. No live-model or scientific-support evaluation was run.",
    }
    serialized = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    print(serialized)
    if args.report:
        args.report.write_text(serialized, encoding="utf-8")


if __name__ == "__main__":
    main()
