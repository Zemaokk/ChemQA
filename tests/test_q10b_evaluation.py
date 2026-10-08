"""Structural citation denominators and honest evaluation freeze guards."""

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from config.settings import settings
from scripts.validate_q10b import (
    check_protocol,
    durable_campaign,
    execute,
    preview,
    report,
)
from src.api_integration.result import GenerationResult
from src.evaluation.citations import citation_statistics
from src.evaluation.comparison import summarize_results
from src.evaluation.dataset import validate_dataset
from src.qa_system.context_selection import select_context
from src.utils.artifacts import sha256_file, write_json
from tests.test_q01_identity import identified


def frozen_protocol():
    return json.loads(Path("config/q10b_protocol.json").read_text())


class CitationMetricsTests(unittest.TestCase):
    def setUp(self):
        self.a = identified("a.pdf", b"a", "first")
        self.b = identified("a.pdf", b"a", "second", 1)
        self.c = identified("c.pdf", b"c", "third")

    def test_repeated_markers_and_unique_chunks_have_different_denominators(self):
        marker = "[Ref " + self.a["chunk_id"] + "]"
        stats = citation_statistics(
            marker + " " + marker + " [Ref unknown]", [self.a, self.b, self.c]
        )
        self.assertEqual(stats["marker_occurrences"], 3)
        self.assertEqual(stats["marker_resolution_rate"], 2 / 3)
        self.assertEqual(stats["context_chunk_utilization"], 1 / 3)
        self.assertEqual(stats["context_document_utilization"], 1 / 2)
        self.assertIsNone(stats["claim_support_precision"])

    def test_no_citations_are_not_perfect_precision_and_unused_is_not_unsupported(self):
        stats = citation_statistics("plain answer", [self.a])
        self.assertIsNone(stats["marker_resolution_rate"])
        self.assertEqual(stats["context_chunk_utilization"], 0)
        self.assertIsNone(stats["claim_citation_recall"])

    def test_numeric_legacy_and_unknown_markers_are_unresolved_in_new_answers(self):
        stats = citation_statistics("[0] [Ref wrong] [Ref wrong]", [self.a])
        self.assertEqual(stats["unresolved_marker_occurrences"], 3)
        self.assertEqual(stats["marker_resolution_rate"], 0)

    def test_empty_context_ratio_is_missing_not_zero_success(self):
        stats = citation_statistics("no evidence", [])
        self.assertIsNone(stats["context_chunk_utilization"])
        self.assertIsNone(stats["context_document_utilization"])
        self.assertIsNone(stats["marker_resolution_rate"])

    def test_duplicate_alias_context_does_not_inflate_denominator(self):
        stats = citation_statistics(
            "[Ref " + self.a["chunk_id"] + "]", [self.a, copy.deepcopy(self.a)]
        )
        self.assertEqual(stats["context_chunk_count"], 1)
        self.assertEqual(stats["context_chunk_utilization"], 1)


class ComparisonTests(unittest.TestCase):
    def test_failed_truncated_and_unsent_records_do_not_become_quality_scores(self):
        rows = []
        for status, sent, usage, answer in [
            ("success", True, {"prompt_tokens": 5}, "answer"),
            ("truncated", True, {}, None),
            ("no_evidence", False, {}, "local answer"),
        ]:
            rows.append(
                {
                    "question_id": "R01",
                    "arm": "test",
                    "answer": answer,
                    "result": {
                        "status": status,
                        "request_sent": sent,
                        "usage": usage,
                        "elapsed_seconds": 2,
                    },
                    "citation_statistics": None,
                }
            )
        summary = summarize_results(rows)["arms"]["test"]
        self.assertEqual(summary["sent_requests"], 2)
        self.assertEqual(
            summary["usage"]["prompt_tokens"],
            {"reported_sum": 5, "reported_requests": 1, "missing_requests": 1},
        )
        self.assertIsNone(summary["usage"]["completion_tokens"]["reported_sum"])
        self.assertIsNone(summary["scientific_quality_scores"])
        self.assertIsNone(summary["cost"])
        self.assertEqual(
            summary["successful_answer_uniqueness_by_question"]["R01"][
                "successful_repetitions"
            ],
            1,
        )


class ProtocolTests(unittest.TestCase):
    def test_interrupted_campaign_preserves_completed_records(self):
        with (
            tempfile.TemporaryDirectory() as tmp,
            patch.object(settings, "OUTPUT_DIR", tmp),
        ):
            with (
                self.assertRaisesRegex(RuntimeError, "fixture"),
                durable_campaign("approved-fixture") as artifact,
            ):
                write_json(artifact.path / "completed.json", {"status": "success"})
                raise RuntimeError("fixture interruption")
            runs = list((Path(tmp) / "q10b_generation").glob("*/run.json"))
            self.assertEqual(len(runs), 1)
            self.assertTrue((runs[0].parent / "completed.json").is_file())

    def test_mock_campaign_executes_90_single_attempts_and_cannot_repeat(self):
        protocol = frozen_protocol()
        reserve = json.loads(Path("evaluation/q10b/reserve.json").read_text())[
            "questions"
        ]
        handler = Mock()
        handler.config = {"base_url": "https://llmapi.paratera.com/v1"}
        handler.request_parameters.return_value = {"body": protocol["request_body"]}
        handler.generate_result.return_value = GenerationResult(
            status="success",
            content="fixture answer",
            request_sent=True,
            attempts=1,
            request_parameters={"body": protocol["request_body"]},
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "output").mkdir()
            preview_path = root / "preview"
            preview_path.mkdir()
            inputs = []
            for question in reserve:
                for arm in protocol["arms"]:
                    hits = (
                        []
                        if arm == "direct"
                        else [
                            {
                                "document": identified(
                                    "fixture.pdf", b"fixture", "fixture evidence"
                                ),
                                "score": 1,
                            }
                        ]
                    )
                    policy = protocol[
                        "diverse_context_policy"
                        if arm.endswith("_diverse")
                        else "common_context_policy"
                    ]
                    kwargs = (
                        {"template": protocol["direct_prompt_template"]}
                        if arm == "direct"
                        else {}
                    )
                    selected = select_context(
                        question["question"],
                        hits,
                        policy,
                        protocol["request_body"],
                        **kwargs,
                    )
                    inputs.append(
                        {
                            "question_id": question["question_id"],
                            "question": question["question"],
                            "arm": arm,
                            "evidence": selected.prepared.chunks,
                            "generation_input": selected.prepared.record(),
                        }
                    )
            write_json(preview_path / "requests.json", inputs)
            write_json(
                preview_path / "run.json",
                {
                    "files": {
                        "requests.json": sha256_file(preview_path / "requests.json")
                    }
                },
            )
            write_json(
                root / "docs/Q10B_PREVIEW.json",
                {
                    "preview_run_sha256": sha256_file(preview_path / "run.json"),
                    "artifact_directory": str(preview_path),
                },
            )
            write_json(root / "docs/Q10B_ANNOTATION_REVIEW.json", {"status": "pending"})
            with (
                patch("scripts.validate_q10b.ROOT", root),
                patch("scripts.validate_q10b.replay"),
                patch("scripts.validate_q10b.check_protocol", return_value=protocol),
                patch(
                    "scripts.validate_q10b.validate_dataset",
                    return_value=(None, None, {"reserve": reserve}, None),
                ),
                patch("scripts.validate_q10b.DeepSeekAPIHandler", return_value=handler),
                patch.object(settings, "OUTPUT_DIR", str(root / "output")),
            ):
                execute(preview_path, sha256_file(preview_path / "run.json"))
                self.assertEqual(handler.generate_result.call_count, 90)
                self.assertTrue(
                    all(
                        call.kwargs["max_attempts"] == 1
                        for call in handler.generate_result.call_args_list
                    )
                )
                generated = next(
                    (root / "output/q10b_generation").glob("*/run.json")
                ).parent
                report(generated)
                summary = json.loads((root / "docs/Q10B_RESULTS.json").read_text())
                self.assertEqual(summary["generation_requests"], 90)
                self.assertIsNone(
                    summary["arms"]["direct"]["scientific_quality_scores"]
                )
                first = generated / "R01-direct-r1.json"
                first.write_text(first.read_text() + " ")
                with self.assertRaisesRegex(ValueError, "record changed"):
                    report(generated)
                with self.assertRaises(FileExistsError):
                    execute(preview_path, sha256_file(preview_path / "run.json"))
                self.assertEqual(handler.generate_result.call_count, 90)

    def test_expanded_probes_preserve_reserve_and_do_not_fake_human_review(self):
        _, _, original, _ = validate_dataset(verify_sources=False)
        _, _, expanded, _ = validate_dataset("evaluation/q10b", verify_sources=False)
        self.assertEqual(expanded["reserve"], original["reserve"])
        self.assertEqual(len(expanded["dev"]), 34)
        new = expanded["dev"][20:]
        self.assertTrue(
            all(
                q["derived_from_question_id"]
                in {p["question_id"] for p in original["dev"]}
                for q in new
            )
        )
        self.assertTrue(all(q["annotation"]["review_status"] == "pending" for q in new))

    def test_frozen_protocol_rejects_modified_dataset_and_component(self):
        protocol = frozen_protocol()
        actual_hash = sha256_file
        runs = {
            str(Path(protocol["source_H_profile"]).parent / "run.json"): protocol[
                "source_H_run_sha256"
            ],
            str(Path(protocol["source_F_directory"]) / "run.json"): protocol[
                "source_F_run_sha256"
            ],
        }

        def checksum(path):
            return runs[str(path)] if str(path) in runs else actual_hash(path)

        for change in [
            {"dataset_manifest_sha256": "changed"},
            {"repetitions": 1},
            {"request_cap": 1},
            {"fixed_files_sha256": {"config/prompts.py": "changed"}},
        ]:
            with (
                patch(
                    "scripts.validate_q10b.read", return_value={**protocol, **change}
                ),
                patch("scripts.validate_q10b.sha256_file", side_effect=checksum),
                patch.object(settings, "DOMAIN", protocol["domain"]),
                self.assertRaises(ValueError),
            ):
                check_protocol()

    def test_reserve_consumption_marker_prevents_reranking_before_model_load(self):
        protocol = frozen_protocol()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "output").mkdir()
            (root / "output/Q10B_RESERVE_CONSUMED.json").write_text("{}")
            with (
                patch("scripts.validate_q10b.ROOT", root),
                patch("scripts.validate_q10b.check_protocol", return_value=protocol),
                patch(
                    "scripts.validate_q10b.validate_dataset",
                    return_value=(None, None, {"reserve": []}, None),
                ),
                patch("scripts.validate_q10b.load_inputs", new=Mock()) as load,
                self.assertRaises(FileExistsError),
            ):
                preview("cpu")
            load.assert_not_called()


if __name__ == "__main__":
    unittest.main()
