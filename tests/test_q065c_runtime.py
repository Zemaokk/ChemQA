"""Device fallback and no-truncation guards for compatibility probes."""

import unittest

from scripts.validate_q065c import checked_token_counts, cpu_fallback, select_device


class RuntimeCompatibilityTests(unittest.TestCase):
    def test_unavailable_mps_selects_cpu_with_reason(self):
        self.assertEqual(select_device("auto", False), ("cpu", "mps_unavailable"))
        self.assertEqual(select_device("mps", False), ("cpu", "mps_unavailable"))

    def test_cpu_override_and_available_mps(self):
        self.assertEqual(select_device("cpu", True), ("cpu", None))
        self.assertEqual(select_device("auto", True), ("mps", None))
        with self.assertRaises(ValueError):
            select_device("cuda", False)

    def test_runtime_accelerator_failure_retries_on_cpu(self):
        calls = []

        def operation(device):
            calls.append(device)
            if device == "mps":
                raise RuntimeError("accelerator unavailable")
            return "cpu result"

        self.assertEqual(cpu_fallback(operation, "mps"), ("cpu result", "RuntimeError"))
        self.assertEqual(calls, ["mps", "cpu"])

    def test_cpu_failure_propagates(self):
        def operation(device):
            raise RuntimeError("cpu failure")

        with self.assertRaisesRegex(RuntimeError, "cpu failure"):
            cpu_fallback(operation, "cpu")

    def test_programming_error_is_not_hidden_by_device_fallback(self):
        def operation(device):
            raise ValueError("bad input")

        with self.assertRaises(ValueError):
            cpu_fallback(operation, "mps")

    def test_prompt_tokens_counted_without_truncation(self):
        class Tokenizer:
            def __call__(self, text, **kwargs):
                assert kwargs == {"add_special_tokens": True, "truncation": False}
                return {"input_ids": list(range(len(text.split()) + 2))}

        self.assertEqual(
            checked_token_counts(Tokenizer(), ["instruction query"], 4), [4]
        )
        with self.assertRaises(ValueError):
            checked_token_counts(Tokenizer(), ["instruction long query"], 4)
