"""Audit real retrieval -> API payload -> saved evidence with all HTTP requests mocked."""

import argparse
import hashlib
import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

from config.settings import settings
from src.qa_system.citation_analyzer import CitationAnalyzer
from src.qa_system.expert_system import ChemicalQAExpert


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    paths = [
        Path(settings.VECTOR_DB_DIR) / "vector_index.json",
        Path(settings.PROCESSED_DIR) / "processed_chunks.json",
    ]
    before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    expert = ChemicalQAExpert()
    expert.generator.api_handler.config = {
        **expert.generator.api_handler.config,
        "api_key": "offline-validation-only",
    }
    # Replace headers too, so the intercepted call cannot contain a configured credential.
    expert.generator.api_handler.headers = {"Content-Type": "application/json"}
    request_prompts = []
    request_ids = []

    def offline_response(*args, **kwargs):
        messages = kwargs["json"]["messages"]
        if len(messages) != 1 or messages[0]["role"] != "user":
            raise ValueError("Unexpected API message structure")
        prompt = messages[0]["content"]
        marker = "检索证据（JSON）：\n"
        evidence, _ = json.JSONDecoder().raw_decode(prompt.split(marker, 1)[1])
        ids = [e["chunk_id"] for e in evidence["evidence"]]
        if evidence["evidence_count"] != len(ids) or not ids:
            raise ValueError("Real retrieval provided no auditable evidence")
        for item in evidence["evidence"]:
            if item["citation"] != f"[Ref {item['chunk_id']}]":
                raise ValueError(
                    "Evidence marker differs from canonical chunk identity"
                )
        request_prompts.append(prompt)
        request_ids.append(ids)
        # Synthetic output tests citation plumbing, not model factual correctness.
        response = Mock(status_code=200)
        response.json.return_value = {
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {
                        "content": f"Offline validation fixture {evidence['evidence'][0]['citation']}. Invalid [Ref 0] [1] [Ref invented]."
                    },
                }
            ]
        }
        return response

    questions = [
        "electrochemical oxidation of alcohols to aldehydes",
        "electrochemical reduction of carbonyl compounds",
    ]
    runs = []
    with tempfile.TemporaryDirectory(prefix="chemqa-q05-") as folder:
        with (
            patch(
                "src.api_integration.api_handler.requests.post",
                side_effect=offline_response,
            ) as post,
            patch("src.utils.artifacts.settings.OUTPUT_DIR", folder),
        ):
            for question in questions:
                answer = expert.answer_query(question, analyze_citations=False)
                saved = json.loads(
                    (expert.last_run_dir / "answer.evidence.json").read_text()
                )
                generation = saved["generation_input"]
                if generation["prompt"] != request_prompts[-1]:
                    raise ValueError("Saved prompt differs from actual API payload")
                data = json.loads(generation["serialized_context"])
                chunks = saved["evidence_map"]
                ids = [c["chunk_id"] for c in chunks]
                if ids != generation["allowed_chunk_ids"] or ids != request_ids[-1]:
                    raise ValueError(
                        "Generation and saved evidence have different identities"
                    )
                if [e["text"] for e in data["evidence"]] != [c["text"] for c in chunks]:
                    raise ValueError("Generation changed or truncated evidence text")
                if [e["page_numbers"] for e in data["evidence"]] != [
                    c["page_numbers"] for c in chunks
                ]:
                    raise ValueError("Generation changed source page numbers")
                analysis = CitationAnalyzer().analyze_citations(
                    saved["raw_answer"], chunks, allow_legacy=False
                )
                if (
                    analysis["citation_coverage"]["cited_count"] != 1
                    or analysis["unresolved_citations"] != saved["unresolved_citations"]
                    or len(saved["unresolved_citations"]) != 3
                    or answer.count("未解析引用：") != 3
                ):
                    raise ValueError("Strict citation parsing differs across consumers")
                runs.append(
                    {
                        "question": question,
                        "evidence_count": len(chunks),
                        "allowed_chunk_ids": ids,
                        "context_version": generation["context_version"],
                        "prompt_version": generation["prompt_version"],
                        "template_sha256": generation["template_sha256"],
                        "prompt_sha256": hashlib.sha256(
                            generation["prompt"].encode()
                        ).hexdigest(),
                        "prompt_characters": len(generation["prompt"]),
                        "cited_chunk_id": ids[0],
                        "unresolved_reasons": [
                            u["reason"] for u in saved["unresolved_citations"]
                        ],
                        "payload_and_sidecar_match": True,
                    }
                )
        if post.call_count != len(questions):
            raise ValueError("Unexpected HTTP call count")
    after = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    if before != after:
        raise ValueError("Prompt validation changed indexed data")
    report = {
        "runs": runs,
        "mocked_http_requests": len(questions),
        "external_api_requests": 0,
        "data_files_unchanged": True,
        "sha256": after,
        "scope": "Real retrieval and actual API-payload serialization; synthetic answers only, no model quality evaluation.",
    }
    serialized = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    print(serialized)
    if args.report:
        args.report.write_text(serialized, encoding="utf-8")


if __name__ == "__main__":
    main()
