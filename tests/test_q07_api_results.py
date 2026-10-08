"""Failures and incomplete completions must not enter answer or success paths."""

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import requests

import main
from qa_testing.direct_api_test import EnhancedAPITester
from qa_testing.test_organic_electrocatalysis_qa import OrganicElectrocatalysisQATester
from src.api_integration.api_generator import DeepSeekAnswerGenerator
from src.api_integration.api_handler import DeepSeekAPIHandler
from src.api_integration.result import (
    APIGenerationError,
    GenerationResult,
    execution_status,
)
from src.qa_system.expert_system import ChemicalQAExpert
from src.qa_system.response_formatter import ResponseFormatter
from tests.test_q01_identity import identified


def response(content="Valid answer", reason="stop", status=200):
    result = Mock(status_code=status)
    result.json.return_value = {
        "id": "fixture-id",
        "model": "fixture-model",
        "usage": {"prompt_tokens": 12, "completion_tokens": 8, "total_tokens": 20},
        "choices": [
            {
                "message": {"role": "assistant", "content": content},
                "finish_reason": reason,
            }
        ],
    }
    return result


class APIResultTests(unittest.TestCase):
    def setUp(self):
        self.handler = DeepSeekAPIHandler()
        self.handler.config["api_key"] = "fixture-key"

    def test_success_preserves_metadata_and_text_wrapper(self):
        with patch(
            "src.api_integration.api_handler.requests.post", return_value=response()
        ) as post:
            result = self.handler.generate_result("prompt")
            self.assertEqual(result.status, "success")
            self.assertEqual(result.require_content(), "Valid answer")
            self.assertEqual(result.returned_model, "fixture-model")
            self.assertEqual(result.response_id, "fixture-id")
            self.assertEqual(result.usage["total_tokens"], 20)
            self.assertEqual(result.attempts, 1)
            self.assertTrue(result.request_sent)
            self.assertEqual(post.call_count, 1)
        with patch.object(self.handler, "generate_result", return_value=result):
            self.assertEqual(self.handler.generate_response("prompt"), "Valid answer")

    def test_missing_key_is_unsent_structured_failure_and_value_error(self):
        self.handler.config["api_key"] = ""
        with patch("src.api_integration.api_handler.requests.post") as post:
            result = self.handler.generate_result("prompt")
            self.assertEqual(result.error_code, "configuration")
            self.assertFalse(result.request_sent)
            self.assertEqual(result.attempts, 0)
            with self.assertRaises(ValueError) as error:
                result.require_content()
            self.assertIs(error.exception.result, result)
            post.assert_not_called()

    def test_permanent_http_errors_are_not_retried_or_exposed_as_answers(self):
        for status in (400, 401, 402, 403, 404, 422):
            with (
                self.subTest(status=status),
                patch(
                    "src.api_integration.api_handler.requests.post",
                    return_value=response(status=status),
                ) as post,
                patch("src.api_integration.api_handler.time.sleep") as sleep,
            ):
                result = self.handler.generate_result("prompt")
                self.assertEqual(result.http_status, status)
                self.assertFalse(result.retryable)
                self.assertIsNone(result.content)
                with self.assertRaises(APIGenerationError):
                    result.require_content()
                self.assertEqual(post.call_count, 1)
                sleep.assert_not_called()

    def test_rate_limit_and_server_error_retry_by_status_then_recover(self):
        with (
            patch(
                "src.api_integration.api_handler.requests.post",
                side_effect=[response(status=429), response(status=503), response()],
            ) as post,
            patch("src.api_integration.api_handler.time.sleep") as sleep,
        ):
            result = self.handler.generate_result("prompt")
        self.assertEqual(result.status, "success")
        self.assertEqual(result.attempts, 3)
        self.assertEqual(
            [r["http_status"] for r in result.attempt_history], [429, 503, 200]
        )
        self.assertEqual(post.call_count, 3)
        self.assertEqual([c.args[0] for c in sleep.call_args_list], [1, 2])

    def test_retry_exhaustion_has_no_final_sleep(self):
        with (
            patch(
                "src.api_integration.api_handler.requests.post",
                return_value=response(status=500),
            ) as post,
            patch("src.api_integration.api_handler.time.sleep") as sleep,
        ):
            result = self.handler.generate_result("prompt")
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.attempts, 3)
        self.assertEqual(post.call_count, 3)
        self.assertEqual(sleep.call_count, 2)

    def test_timeout_and_network_failures_are_distinct_and_redacted(self):
        for exception, code in (
            (requests.Timeout("fixture-key secret"), "timeout"),
            (requests.ConnectionError("fixture-key secret"), "network"),
        ):
            with (
                self.subTest(code=code),
                patch(
                    "src.api_integration.api_handler.requests.post",
                    side_effect=exception,
                ),
                patch("src.api_integration.api_handler.time.sleep"),
            ):
                result = self.handler.generate_result("prompt")
                self.assertEqual(result.error_code, code)
                self.assertEqual(result.attempts, 3)
                self.assertNotIn("fixture-key", json.dumps(result.record()))

    def test_length_is_quarantined_without_retry(self):
        with (
            patch(
                "src.api_integration.api_handler.requests.post",
                return_value=response("Incomplete claim", "length"),
            ) as post,
            patch("src.api_integration.api_handler.time.sleep") as sleep,
        ):
            result = self.handler.generate_result("prompt")
        self.assertEqual(result.status, "truncated")
        self.assertEqual(result.partial_content, "Incomplete claim")
        self.assertIsNone(result.content)
        self.assertEqual(result.usage["total_tokens"], 20)
        self.assertEqual(post.call_count, 1)
        sleep.assert_not_called()
        with self.assertRaises(APIGenerationError):
            result.require_content()

    def test_other_finish_reasons_never_become_normal_answers(self):
        for reason in (
            "content_filter",
            "tool_calls",
            "aborted",
            "insufficient_system_resource",
            "unknown",
        ):
            with (
                self.subTest(reason=reason),
                patch(
                    "src.api_integration.api_handler.requests.post",
                    return_value=response("Partial", reason),
                ),
                patch("src.api_integration.api_handler.time.sleep"),
            ):
                result = self.handler.generate_result("prompt")
                self.assertFalse(result.completed)
                self.assertEqual(
                    result.attempts,
                    3 if reason == "insufficient_system_resource" else 1,
                )

    def test_invalid_json_structure_empty_and_reasoning_only_fail(self):
        payloads = [
            None,
            [],
            {},
            {"choices": []},
            {"choices": [None]},
            {"choices": [{"message": {"content": "answer"}}]},
            {"choices": [{"message": None, "finish_reason": "stop"}]},
        ]
        for content in (None, "", " \n", [], 17):
            payloads.append(response(content).json.return_value)
        payloads.append({**response().json.return_value, "error": {"message": "error"}})
        for field, value in (("role", "user"), ("tool_calls", [{"id": "tool"}])):
            payload = response().json.return_value
            payload["choices"][0]["message"][field] = value
            payloads.append(payload)
        payloads.append(
            {
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"reasoning_content": "Only reasoning"},
                    }
                ]
            }
        )
        for payload in payloads:
            mock = response()
            mock.json.return_value = payload
            with (
                self.subTest(payload=payload),
                patch(
                    "src.api_integration.api_handler.requests.post", return_value=mock
                ) as post,
            ):
                result = self.handler.generate_result("prompt")
                self.assertEqual(result.error_code, "invalid_response")
                self.assertEqual(post.call_count, 1)
        mock = response()
        mock.json.side_effect = ValueError("untrusted body fixture-key")
        with patch("src.api_integration.api_handler.requests.post", return_value=mock):
            result = self.handler.generate_result("prompt")
        self.assertNotIn("fixture-key", json.dumps(result.record()))

    def test_http_error_does_not_read_provider_body(self):
        mock = response(status=401)
        mock.text = "fixture-key secret provider body"
        with patch("src.api_integration.api_handler.requests.post", return_value=mock):
            result = self.handler.generate_result("prompt")
        self.assertNotIn("fixture-key", json.dumps(result.record()))
        mock.json.assert_not_called()

    def test_invalid_arguments_fail_before_network(self):
        with patch("src.api_integration.api_handler.requests.post") as post:
            for value in (0, -1, True, 1.5):
                with self.assertRaises(ValueError):
                    self.handler.generate_result("prompt", max_attempts=value)
            for prompt in (None, "", " "):
                with self.assertRaises(ValueError):
                    self.handler.generate_result(prompt)
            post.assert_not_called()


class PipelineResultTests(unittest.TestCase):
    def expert(self, context):
        expert = ChemicalQAExpert.__new__(ChemicalQAExpert)
        expert.retriever = Mock()
        expert.retriever.retrieve_relevant_context.return_value = context
        expert.generator = DeepSeekAnswerGenerator()
        expert.generator.api_handler.config["api_key"] = "fixture-key"
        expert.formatter = ResponseFormatter()
        expert._analyze_citations = Mock()
        return expert

    def test_failure_does_not_format_analyze_or_overwrite_existing_answer(self):
        for completion in (response(status=401), response("Partial claim", "length")):
            with (
                self.subTest(status=completion.status_code),
                tempfile.TemporaryDirectory() as folder,
            ):
                root = Path(folder)
                (root / "answer_6.md").write_text("previous valid answer")
                (root / "answer_6.evidence.json").write_text("previous evidence")
                expert = self.expert([identified("p.pdf", b"p", "Evidence")])
                expert.formatter = Mock()
                with (
                    patch("src.utils.artifacts.settings.OUTPUT_DIR", str(root)),
                    patch(
                        "src.api_integration.api_handler.requests.post",
                        return_value=completion,
                    ),
                    self.assertRaises(APIGenerationError),
                ):
                    expert.answer_query("q")
                self.assertEqual(
                    (root / "answer_6.md").read_text(), "previous valid answer"
                )
                self.assertEqual(
                    (root / "answer_6.evidence.json").read_text(), "previous evidence"
                )
                failure = json.loads((expert.last_run_dir / "failure.json").read_text())
                self.assertIsNone(failure["raw_answer"])
                self.assertTrue(failure["generation_input"]["prompt_sent"])
                self.assertFalse(
                    failure["generation_input"]["decision"][
                        "scientific_support_verified"
                    ]
                )
                expert.formatter.format.assert_not_called()
                expert._analyze_citations.assert_not_called()

    def test_missing_key_failure_preserves_unsent_prompt(self):
        expert = self.expert([identified("p.pdf", b"p", "Evidence")])
        expert.generator.api_handler.config["api_key"] = ""
        with (
            tempfile.TemporaryDirectory() as folder,
            patch("src.utils.artifacts.settings.OUTPUT_DIR", folder),
            patch("src.api_integration.api_handler.requests.post") as post,
        ):
            with self.assertRaises(ValueError):
                expert.answer_query("q")
            failure = json.loads((expert.last_run_dir / "failure.json").read_text())
            self.assertFalse(failure["generation_input"]["prompt_sent"])
            self.assertEqual(failure["generation_result"]["attempts"], 0)
            post.assert_not_called()

    def test_empty_evidence_has_its_own_completed_local_status(self):
        expert = self.expert([])
        with patch("src.api_integration.api_handler.requests.post") as post:
            result = expert.generator.generate_answer_result("q", [])
        self.assertEqual(result.status, "no_evidence")
        self.assertTrue(result.completed)
        self.assertFalse(result.request_sent)
        self.assertEqual(result.attempts, 0)
        post.assert_not_called()

    def test_direct_batch_failure_is_not_saved_as_an_answer(self):
        tester = EnhancedAPITester.__new__(EnhancedAPITester)
        tester.api_handler = DeepSeekAPIHandler()
        tester.api_handler.config["api_key"] = "fixture-key"
        tester.prompt_template = "Question: {question}"
        with (
            tempfile.TemporaryDirectory() as folder,
            patch(
                "src.api_integration.api_handler.requests.post",
                return_value=response("Partial", "length"),
            ),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            tester.output_dir = Path(folder)
            result = tester.run_single_test_with_retry("q", 1)
            self.assertEqual(result["status"], "truncated")
            self.assertNotIn("answer", result)
            self.assertFalse((Path(folder) / "enhanced_answer_01.md").exists())
            self.assertTrue((Path(folder) / "enhanced_failure_01.json").exists())

    def test_rag_batch_failure_does_not_analyze_citations(self):
        tester = OrganicElectrocatalysisQATester.__new__(
            OrganicElectrocatalysisQATester
        )
        tester.expert = self.expert([identified("p.pdf", b"p", "Evidence")])
        with (
            tempfile.TemporaryDirectory() as folder,
            patch(
                "src.api_integration.api_handler.requests.post",
                return_value=response(status=401),
            ),
            patch(
                "qa_testing.test_organic_electrocatalysis_qa.analyze_answer_citations"
            ) as analyze,
            contextlib.redirect_stdout(io.StringIO()),
        ):
            tester.output_dir = Path(folder)
            result = tester.run_single_test("q", 1)
            self.assertEqual(result["status"], "failed")
            analyze.assert_not_called()
            self.assertFalse((Path(folder) / "answer_01.md").exists())

    def test_batch_summary_does_not_infer_historical_success(self):
        self.assertEqual(
            execution_status({"answer": "API Error: old failure"}), "unverified"
        )
        common = {
            "question_id": 1,
            "question": "q",
            "processing_time": 1,
            "answer_length": 5,
            "context_count": 1,
            "citation_analysis": {"citation_coverage": {"coverage_percentage": 0}},
        }
        results = [
            {**common, "status": "success"},
            {**common, "status": "truncated", "error": "length"},
            {**common, "answer": "API Error: old failure"},
            {**common, "status": "pending"},
        ]
        for cls, filename in (
            (EnhancedAPITester, "enhanced_api_summary.json"),
            (OrganicElectrocatalysisQATester, "test_summary.json"),
        ):
            with (
                self.subTest(tester=cls.__name__),
                tempfile.TemporaryDirectory() as folder,
                contextlib.redirect_stdout(io.StringIO()),
            ):
                tester = cls.__new__(cls)
                batch_results = list(results)
                if cls is OrganicElectrocatalysisQATester:
                    batch_results.append({**common, "status": "no_evidence"})
                tester.output_dir, tester.questions, tester.results = (
                    Path(folder),
                    ["q"] * len(batch_results),
                    batch_results,
                )
                if cls is EnhancedAPITester:
                    tester.save_summary_results()
                else:
                    tester.save_summary_results(1)
                info = json.loads((Path(folder) / filename).read_text())["test_info"]
                self.assertEqual(info["successful_tests"], 1)
                self.assertEqual(info["failed_tests"], 1)
                self.assertEqual(info["unverified_tests"], 1)
                self.assertEqual(info["truncated_tests"], 1)
                self.assertEqual(info["pending_tests"], 1)
                if cls is OrganicElectrocatalysisQATester:
                    self.assertEqual(info["no_evidence_tests"], 1)

    def test_cli_failure_exits_nonzero_and_interactive_loop_can_continue(self):
        error = APIGenerationError(
            GenerationResult(
                status="failed",
                error_code="http",
                error_message="API returned HTTP 401.",
            )
        )
        with (
            patch("main.ChemicalQAExpert") as expert,
            patch("sys.argv", ["main.py", "-q", "q"]),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            expert.return_value.answer_query.side_effect = error
            with self.assertRaises(SystemExit) as exit_result:
                main.main()
            self.assertEqual(exit_result.exception.code, 1)
        with (
            patch("main.ChemicalQAExpert") as expert,
            patch("sys.argv", ["main.py"]),
            patch("builtins.input", side_effect=["q", "exit"]),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            expert.return_value.answer_query.side_effect = error
            main.main()
            self.assertEqual(expert.return_value.answer_query.call_count, 1)


if __name__ == "__main__":
    unittest.main()
