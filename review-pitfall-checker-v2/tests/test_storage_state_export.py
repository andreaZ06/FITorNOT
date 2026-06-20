import base64
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import storage_state_export as module


class StorageStateExportHelpersTest(unittest.TestCase):
    def test_encode_storage_state_for_env_returns_base64_prefixed_value(self):
        payload = {
            "cookies": [{"name": "sid", "value": "x", "domain": ".jd.com", "path": "/"}],
            "origins": [],
        }

        encoded = module.encode_storage_state_for_env(payload)

        self.assertTrue(encoded.startswith("base64:"))
        decoded = base64.b64decode(encoded[len("base64:") :]).decode("utf-8")
        self.assertEqual(json.loads(decoded), payload)

    def test_validate_storage_state_rejects_empty_payload(self):
        with self.assertRaisesRegex(ValueError, "must contain at least one cookie or origin"):
            module.validate_storage_state_payload({"cookies": [], "origins": []})

    def test_resolve_profile_dir_uses_fitornot_env_when_present(self):
        with patch.dict("os.environ", {"FITORNOT_BROWSER_PROFILE_DIR": "C:/tmp/fitornot-profile"}, clear=False):
            resolved = module.resolve_profile_dir(None)

        self.assertEqual(resolved, Path("C:/tmp/fitornot-profile"))

    def test_write_storage_state_file_persists_json(self):
        payload = {
            "cookies": [{"name": "sid", "value": "x", "domain": ".jd.com", "path": "/"}],
            "origins": [],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "storage-state.json"
            written = module.write_storage_state_file(payload, output_path)

            self.assertEqual(written, output_path)
            self.assertEqual(json.loads(output_path.read_text(encoding="utf-8")), payload)
