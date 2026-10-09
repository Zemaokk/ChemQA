"""Audit redaction, exact Git-index checks and history-free release boundaries."""

import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.audit_secrets import HISTORY_LIMIT, audit, scan_lines
from scripts.prepare_source_release import prepare
from src.utils.artifacts import sha256_file


class SecretAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.key = "sk-" + "fixtureForPatternAuditOnly123456"
        self.git("init", "-q")
        self.git("config", "user.name", "Audit Fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        self.git("config", "commit.gpgsign", "false")
        self.git("config", "core.hooksPath", "/dev/null")

    def git(self, *args):
        return subprocess.check_output(
            ["git", "-C", str(self.root), *args], stderr=subprocess.DEVNULL
        )

    def commit(self):
        self.git("add", ".")
        self.git("commit", "-qm", "temporary fixture only")

    def test_redaction_preserves_lines_and_occurrence_counts_only(self):
        findings, digests = scan_lines(
            io.BytesIO(f"safe\n{self.key} {self.key}\n".encode())
        )
        self.assertEqual(findings, [{"line": 2, "occurrences": 2}])
        self.assertEqual(len(digests), 1)
        self.assertNotIn(self.key, json.dumps(findings))

    def test_exact_staged_bytes_detect_key_hidden_by_clean_working_file(self):
        file = self.root / "settings.py"
        file.write_text(self.key)
        self.git("add", "settings.py")
        file.write_text("clean working copy")
        self.assertTrue(audit(self.root)["current_clean"])
        staged = audit(self.root, staged=True)
        self.assertFalse(staged["current_clean"])
        self.assertNotIn(self.key, json.dumps(staged))

    def test_history_remains_detectable_after_current_file_is_clean(self):
        file = self.root / "settings.py"
        file.write_text(self.key)
        self.commit()
        file.write_text(self.key + "\n# another version")
        self.commit()
        file.write_text("clean current version")
        self.commit()
        report = audit(self.root, history=True)
        self.assertTrue(report["current_clean"])
        self.assertFalse(report["history_clean"])
        self.assertEqual(report["history"]["distinct_pattern_count"], 1)
        self.assertEqual(len(report["history"]["findings"]), 2)
        self.assertNotIn(self.key, json.dumps(report))

    def test_ignored_env_is_excluded_but_untracked_source_is_checked(self):
        (self.root / ".gitignore").write_text(".env\n")
        (self.root / ".env").write_text(self.key)
        self.assertTrue(audit(self.root)["current_clean"])
        (self.root / "new.py").write_text(self.key)
        self.assertFalse(audit(self.root)["current_clean"])

    def test_oversized_history_exclusion_is_reported(self):
        file = self.root / "large.txt"
        file.write_bytes(b"x" * (HISTORY_LIMIT + 1))
        self.commit()
        file.unlink()
        self.commit()
        report = audit(self.root, history=True)
        self.assertEqual(len(report["history"]["oversized_text_blobs_skipped"]), 1)
        self.assertEqual(report["history"]["text_blobs_scanned"], 0)

    def test_cli_reports_failure_without_disclosing_key(self):
        (self.root / "settings.py").write_text(self.key)
        script = Path(__file__).resolve().parents[1] / "scripts/audit_secrets.py"
        result = subprocess.run(
            [sys.executable, str(script), "--root", str(self.root)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 1)
        self.assertFalse(json.loads(result.stdout)["current_clean"])
        self.assertNotIn(self.key, result.stdout + result.stderr)

    def test_release_excludes_history_env_datasets_and_archived_answers(self):
        (self.root / ".gitignore").write_text(".env\n")
        (self.root / ".env").write_text(self.key)
        for relative in [
            "main.py",
            "README.md",
            "CHANGELOG.md",
            "CONTRIBUTING.md",
            "data/README.md",
            "docs/README.md",
            "docs/how-to/build-index.md",
            "docs/legacy-docs/old.md",
            "legacy-docs/2026-10-09/README.md",
            ".env.example",
            "config/settings.py",
            "data/raw_papers/a.pdf",
            "data/vector_db/vector_index.json",
            "models/README.md",
            "example_answers/a.md",
            "qa_testing/old_answer.md",
            "qa_testing/README.md",
        ]:
            file = self.root / relative
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text("fixture")
        self.commit()
        target = self.root / "prepared"
        prepare(self.root, destination=target)
        self.assertFalse((target / ".git").exists())
        self.assertFalse((target / ".env").exists())
        self.assertTrue((target / "data/README.md").is_file())
        self.assertFalse((target / "data/raw_papers").exists())
        self.assertFalse((target / "data/vector_db").exists())
        self.assertFalse((target / "models").exists())
        self.assertFalse((target / "example_answers").exists())
        self.assertFalse((target / "qa_testing/old_answer.md").exists())
        self.assertFalse((target / "legacy-docs").exists())
        self.assertFalse((target / "docs/legacy-docs").exists())
        for relative in (
            "README.md",
            "CHANGELOG.md",
            "CONTRIBUTING.md",
            "docs/README.md",
            "docs/how-to/build-index.md",
        ):
            self.assertTrue((target / relative).is_file(), relative)
        manifest = json.loads((target / "SOURCE_RELEASE.json").read_text())
        self.assertTrue((target / "config/settings.py").is_file())
        for relative, digest in manifest["files_sha256"].items():
            self.assertEqual(sha256_file(target / relative), digest)
        with self.assertRaises(FileExistsError):
            prepare(self.root, destination=target)

    def test_release_refuses_current_key_and_leaves_no_target(self):
        (self.root / "main.py").write_text(self.key)
        target = self.root / "prepared"
        with self.assertRaisesRegex(ValueError, "key patterns"):
            prepare(self.root, destination=target)
        self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()
