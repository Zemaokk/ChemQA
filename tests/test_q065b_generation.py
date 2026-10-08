"""Explicit generation parameters, provider accounting and frozen input boundaries."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from config.settings import BASE_DIR, settings
from scripts.validate_q065b import load_inputs, prepare_baseline, verify_preview
from src.api_integration.api_handler import DeepSeekAPIHandler
from src.api_integration.result import GenerationResult
from src.utils.artifacts import sha256_file
from tests.test_q07_api_results import response


class GenerationMigrationTests(unittest.TestCase):
    def setUp(self):
        self.handler = DeepSeekAPIHandler()
        self.handler.config.update(
            api_key="fixture-key",
            model="fixture-model",
            thinking="disabled",
            max_attempts=3,
        )

    def test_disabled_mode_budget_timeout_and_redirect_policy(self):
        with patch(
            "src.api_integration.api_handler.requests.post", return_value=response()
        ) as post:
            result = self.handler.generate_result("prompt", max_attempts=1)
        kwargs = post.call_args.kwargs
        self.assertEqual(kwargs["json"]["thinking"], {"type": "disabled"})
        self.assertEqual(kwargs["json"]["max_tokens"], 4096)
        self.assertFalse(kwargs["json"]["stream"])
        self.assertEqual(kwargs["timeout"], (10, 120))
        self.assertFalse(kwargs["allow_redirects"])
        self.assertNotIn("frequency_penalty", kwargs["json"])
        self.assertEqual(result.request_parameters["max_attempts"], 1)
        self.assertNotIn("fixture-key", json.dumps(result.record()))

    def test_thinking_mode_omits_inapplicable_sampling_fields(self):
        self.handler.config["thinking"] = "enabled"
        with patch(
            "src.api_integration.api_handler.requests.post", return_value=response()
        ) as post:
            self.handler.generate_result("prompt")
        body = post.call_args.kwargs["json"]
        self.assertEqual(body["thinking"], {"type": "enabled"})
        self.assertNotIn("temperature", body)
        self.assertNotIn("top_p", body)

    def test_reasoning_accounting_retained_without_reasoning_text(self):
        mock = response()
        data = mock.json.return_value
        data["choices"][0]["message"]["reasoning_content"] = (
            "private reasoning sentinel"
        )
        data["usage"]["completion_tokens_details"] = {
            "reasoning_tokens": 7,
            "ignored": "secret",
        }
        data["usage"]["prompt_tokens_details"] = {"cached_tokens": 3, "ignored": 12}
        with patch("src.api_integration.api_handler.requests.post", return_value=mock):
            result = self.handler.generate_result("prompt")
        self.assertTrue(result.reasoning_content_present)
        self.assertEqual(
            result.usage["completion_tokens_details"], {"reasoning_tokens": 7}
        )
        self.assertEqual(result.usage["prompt_tokens_details"], {"cached_tokens": 3})
        self.assertNotIn("private reasoning sentinel", json.dumps(result.record()))

    def test_missing_usage_stays_unknown(self):
        mock = response()
        del mock.json.return_value["usage"]
        with patch("src.api_integration.api_handler.requests.post", return_value=mock):
            result = self.handler.generate_result("prompt")
        self.assertEqual(result.usage, {})

    def test_attempt_history_preserves_failed_and_successful_usage(self):
        failed = response("Partial", "insufficient_system_resource")
        with (
            patch(
                "src.api_integration.api_handler.requests.post",
                side_effect=[failed, response()],
            ),
            patch("src.api_integration.api_handler.time.sleep"),
        ):
            result = self.handler.generate_result("prompt")
        self.assertEqual(result.attempts, 2)
        for row in result.attempt_history:
            self.assertEqual(row["usage"]["total_tokens"], 20)
            self.assertGreaterEqual(row["elapsed_seconds"], 0)
            self.assertEqual(row["returned_model"], "fixture-model")

    def test_configured_attempt_limit_used_by_default(self):
        self.handler.config["max_attempts"] = 1
        with patch(
            "src.api_integration.api_handler.requests.post",
            return_value=response(status=503),
        ) as post:
            result = self.handler.generate_result("prompt")
        self.assertEqual(result.attempts, 1)
        self.assertEqual(post.call_count, 1)

    def test_bad_parameters_fail_without_network(self):
        for key, value in [
            ("thinking", "auto"),
            ("temperature", float("nan")),
            ("connect_timeout", 0),
            ("read_timeout", -1),
        ]:
            with self.subTest(key=key):
                original = self.handler.config[key]
                self.handler.config[key] = value
                with patch("src.api_integration.api_handler.requests.post") as post:
                    result = self.handler.generate_result("prompt")
                self.handler.config[key] = original
                self.assertEqual(result.error_code, "configuration")
                self.assertFalse(result.request_sent)
                post.assert_not_called()

    def test_redirect_is_failure_without_following(self):
        with patch(
            "src.api_integration.api_handler.requests.post",
            return_value=response(status=307),
        ) as post:
            result = self.handler.generate_result("prompt")
        self.assertEqual(result.http_status, 307)
        self.assertEqual(post.call_count, 1)
        self.assertFalse(result.completed)

    def test_thinking_only_length_is_not_success(self):
        mock = response(None, "length")
        mock.json.return_value["choices"][0]["message"]["reasoning_content"] = (
            "thinking"
        )
        with patch("src.api_integration.api_handler.requests.post", return_value=mock):
            result = self.handler.generate_result("prompt")
        self.assertEqual(result.status, "truncated")
        self.assertTrue(result.reasoning_content_present)
        self.assertIsNone(result.content)

    def test_more_than_five_attempts_rejected(self):
        with self.assertRaises(ValueError):
            self.handler.generate_result("prompt", max_attempts=6)

    def test_frozen_dev_prompts_use_retrieved_context_and_no_provider(self):
        with patch("src.api_integration.api_handler.requests.post") as post:
            report, _, _, inputs = load_inputs(
                Path(BASE_DIR) / "docs/Q10A_BASELINE.json"
            )
        self.assertEqual(len(inputs), 20)
        self.assertEqual([q["question_id"] for q, _ in inputs], report["question_ids"])
        self.assertTrue(all(q["split"] == "dev" for q, _ in inputs))
        post.assert_not_called()

    def test_result_does_not_invent_reasoning_or_usage(self):
        result = GenerationResult(status="success", content="Answer")
        self.assertFalse(result.reasoning_content_present)
        self.assertEqual(result.usage, {})

    def test_local_preview_is_unsent_and_rejects_changed_prompt(self):
        report_path = Path(BASE_DIR) / "docs/Q10A_BASELINE.json"
        with (
            tempfile.TemporaryDirectory() as temporary,
            patch.object(settings, "OUTPUT_DIR", temporary),
            patch("src.api_integration.api_handler.requests.post") as post,
        ):
            preview = prepare_baseline(report_path)
            root = Path(preview["artifact_directory"])
            _, _, _, inputs = load_inputs(report_path)
            handler = DeepSeekAPIHandler()
            handler.config["max_attempts"] = 1
            profile = handler.request_parameters()
            self.assertEqual(preview["generation_requests"], 0)
            self.assertEqual(len(preview["files_sha256"]), 20)
            verify_preview(root, inputs, profile, report_path)
            path = root / "D01.json"
            data = json.loads(path.read_text())
            data["generation_input"]["prompt"] += " changed"
            path.write_text(json.dumps(data))
            protocol_path = root / "protocol.json"
            protocol = json.loads(protocol_path.read_text())
            protocol["files_sha256"]["D01.json"] = sha256_file(path)
            protocol_path.write_text(json.dumps(protocol))
            with self.assertRaisesRegex(ValueError, "prompt changed"):
                verify_preview(root, inputs, profile, report_path)
            post.assert_not_called()

    def test_changed_preview_profile_rejected(self):
        report_path = Path(BASE_DIR) / "docs/Q10A_BASELINE.json"
        with (
            tempfile.TemporaryDirectory() as temporary,
            patch.object(settings, "OUTPUT_DIR", temporary),
        ):
            preview = prepare_baseline(report_path)
            _, _, _, inputs = load_inputs(report_path)
            profile = preview["request_parameters"]
            profile["body"]["max_tokens"] += 1
            with self.assertRaisesRegex(ValueError, "configuration"):
                verify_preview(
                    Path(preview["artifact_directory"]), inputs, profile, report_path
                )
