"""Check integrity refusal and secret exclusion in upgrade-reference artifacts."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from config.settings import settings
from scripts.validate_q065a import (
    check_bundle,
    digest,
    restore,
    safe_config,
    write_json,
)


class ReferenceTests(unittest.TestCase):
    def test_config_excludes_credential_value(self):
        with patch.dict(settings.DEEPSEEK_API_CONFIG, api_key="sentinel-secret"):
            config = safe_config()
        self.assertTrue(config["api_key_configured"])
        self.assertNotIn("sentinel-secret", json.dumps(config))
        self.assertNotIn("api_key", config)

    def test_bundle_rejects_changed_or_missing_artifact(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact = root / "payload"
            artifact.write_bytes(b"original")
            write_json(
                root / "manifest.json",
                {"files": {"payload": {"sha256": digest(artifact)}}},
            )
            self.assertIn("files", check_bundle(root))
            artifact.write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "Reference artifact changed"):
                check_bundle(root)
            artifact.unlink()
            with self.assertRaises(FileNotFoundError):
                check_bundle(root)

    def test_restore_refuses_existing_destination(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_json(root / "manifest.json", {"files": {}})
            with self.assertRaises(FileExistsError):
                restore(root, root)


if __name__ == "__main__":
    unittest.main()
