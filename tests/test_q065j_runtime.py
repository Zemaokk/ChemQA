"""Frozen runtime validation and rollback must work without models or API calls."""

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from config.settings import settings
from src.qa_system.runtime_profile import configure_runtime, validate_runtime
from src.utils.artifacts import sha256_file


class RuntimeFreezeTests(unittest.TestCase):
    def setUp(self):
        self.original = copy.deepcopy(settings.__dict__)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(self.restore_settings)
        self.root = Path(self.temp.name)
        artifact = self.root / "index.json"
        artifact.write_text("fixture")
        self.artifact = artifact
        self.manifest = json.loads(Path("config/q065j_runtime.json").read_text())
        self.manifest["shared_files_sha256"] = {}
        for profile in self.manifest["profiles"].values():
            profile["files_sha256"] = {str(artifact): sha256_file(artifact)}
        self.path = self.root / "freeze.json"
        self.save()

    def restore_settings(self):
        settings.__dict__.clear()
        settings.__dict__.update(self.original)

    def save(self):
        self.path.write_text(json.dumps(self.manifest))

    def test_drift_rejected_before_any_setting_changes(self):
        before = copy.deepcopy(settings.__dict__)
        self.artifact.write_text("changed")
        with self.assertRaisesRegex(ValueError, "missing or changed"):
            configure_runtime("legacy", manifest_path=self.path)
        self.assertEqual(settings.__dict__, before)

    def test_missing_artifact_rejected(self):
        self.artifact.unlink()
        with self.assertRaisesRegex(ValueError, "missing or changed"):
            validate_runtime("hybrid_rerank", manifest_path=self.path)

    def test_rollback_clears_candidate_and_environment_overrides_keeps_key(self):
        settings.EMBEDDING_PROFILE = "candidate"
        settings.DEEPSEEK_API_CONFIG = {
            **settings.DEEPSEEK_API_CONFIG,
            "api_key": "fixture-secret",
            "model": "override",
        }
        options, provenance = configure_runtime("legacy", manifest_path=self.path)
        self.assertEqual(options, {"reranker_profile": None, "context_policy": None})
        self.assertIsNone(settings.EMBEDDING_PROFILE)
        self.assertTrue(settings.VECTOR_DB_DIR.endswith("data/vector_db"))
        self.assertTrue(settings.PROCESSED_DIR.endswith("data/processed"))
        self.assertEqual(settings.DEEPSEEK_API_CONFIG["api_key"], "fixture-secret")
        self.assertEqual(settings.DEEPSEEK_API_CONFIG["model"], "DeepSeek-V4-Flash")
        self.assertNotIn("fixture-secret", json.dumps(provenance))

    def test_candidate_uses_exact_evaluated_policy(self):
        protocol = json.loads(Path("config/q10b_protocol.json").read_text())
        policy = json.loads(Path("config/q065j_context.json").read_text())
        self.assertEqual(policy, protocol["common_context_policy"])
        options, _ = configure_runtime("hybrid_rerank", manifest_path=self.path)
        self.assertEqual(options["context_policy"], "config/q065j_context.json")
        self.assertEqual(settings.EMBEDDING_PROFILE, "config/q065e_embedding.json")
        self.assertEqual(settings.MAX_TOKENS, 4096)

    def test_cli_rejects_mixed_index_and_freeze_without_loading_models(self):
        result = subprocess.run(
            [
                sys.executable,
                "main.py",
                "--runtime-profile",
                "legacy",
                "--index-dir",
                "other",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("cannot be combined", result.stderr)

    def test_freeze_does_not_claim_human_approval_or_change_implicit_default(self):
        self.assertEqual(self.manifest["default_retrieval"], "legacy")
        self.assertEqual(
            self.manifest["adoption_status"],
            "engineering_frozen_assistant_review_complete_default_retained",
        )
        self.assertFalse(self.manifest["review_gate"]["independent_human_approval"])
        self.assertEqual(
            self.manifest["generation"]["body"],
            json.loads(Path("config/q10b_protocol.json").read_text())["request_body"],
        )


if __name__ == "__main__":
    unittest.main()
