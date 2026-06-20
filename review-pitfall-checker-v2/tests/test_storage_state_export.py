import contextlib
import io
import base64
import importlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

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


class StorageStateExportCliTest(unittest.TestCase):
    def test_build_export_summary_includes_railway_env_value(self):
        payload = {
            "cookies": [{"name": "sid", "value": "x", "domain": ".jd.com", "path": "/"}],
            "origins": [],
        }
        output_path = Path("C:/tmp/storage-state.json")

        summary = module.build_export_summary(payload, output_path)

        self.assertEqual(summary["output_path"], str(output_path))
        self.assertTrue(summary["env_value"].startswith("base64:"))
        self.assertIn("FITORNOT_BROWSER_STORAGE_STATE=", summary["env_assignment"])

    def test_assert_profile_dir_exists_rejects_missing_directory(self):
        with self.assertRaisesRegex(FileNotFoundError, "Profile directory does not exist"):
            module.assert_profile_dir_exists(Path("C:/definitely-missing-fitornot-profile"))

    def test_main_success_prints_ready_to_paste_railway_assignment(self):
        export_module = importlib.import_module("export_fitornot_storage_state")
        stdout = io.StringIO()
        summary = {
            "output_path": "C:/tmp/storage-state.json",
            "env_value": "base64:encoded-value",
            "env_assignment": "FITORNOT_BROWSER_STORAGE_STATE=base64:encoded-value",
        }

        with patch.object(export_module, "export_storage_state", new=AsyncMock(return_value=summary)):
            with contextlib.redirect_stdout(stdout):
                exit_code = export_module.main(
                    ["--profile-dir", "C:/tmp/fitornot-profile", "--output", "C:/tmp/storage-state.json"]
                )

        output = stdout.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertIn("Paste this into Railway", output)
        self.assertIn(summary["env_assignment"], output)
