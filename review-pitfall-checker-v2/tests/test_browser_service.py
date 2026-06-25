import importlib
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


class BrowserServiceTest(unittest.TestCase):
    def setUp(self):
        self._original_env = os.environ.copy()
        for key in list(os.environ):
            if key.startswith("FITORNOT_BROWSER_") or key.startswith("FITORNOT_SERVICE_") or key == "PORT":
                os.environ.pop(key, None)
        sys.modules.pop("browser_service", None)
        sys.modules.pop("service_launcher", None)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._original_env)
        sys.modules.pop("browser_service", None)
        sys.modules.pop("service_launcher", None)

    def test_build_browser_service_config_uses_public_port_and_defaults(self):
        os.environ["PORT"] = "38080"
        module = importlib.import_module("browser_service")

        config = module.build_browser_service_config()

        self.assertEqual(config.public_port, 38080)
        self.assertEqual(config.cdp_port, 9222)
        self.assertEqual(config.vnc_port, 5900)
        self.assertEqual(config.display, ":99")
        self.assertTrue(str(config.profile_dir).endswith(".browser-profile"))
        self.assertEqual(config.start_url, "https://www.jd.com/")

    def test_build_browser_service_config_honors_explicit_env_overrides(self):
        os.environ["PORT"] = "38080"
        os.environ["FITORNOT_BROWSER_PUBLIC_PORT"] = "39090"
        os.environ["FITORNOT_BROWSER_CDP_PORT"] = "9333"
        os.environ["FITORNOT_BROWSER_VNC_PORT"] = "5999"
        os.environ["FITORNOT_BROWSER_DISPLAY"] = ":88"
        os.environ["FITORNOT_BROWSER_START_URL"] = "https://www.taobao.com/"
        os.environ["FITORNOT_BROWSER_PROFILE_DIR"] = "/data/fitornot-browser"
        module = importlib.import_module("browser_service")

        config = module.build_browser_service_config()

        self.assertEqual(config.public_port, 39090)
        self.assertEqual(config.cdp_port, 9333)
        self.assertEqual(config.vnc_port, 5999)
        self.assertEqual(config.display, ":88")
        self.assertEqual(config.start_url, "https://www.taobao.com/")
        self.assertEqual(config.profile_dir, Path("/data/fitornot-browser"))

    def test_prepare_novnc_web_root_copies_assets_and_adds_health_file(self):
        module = importlib.import_module("browser_service")

        with tempfile.TemporaryDirectory() as source_dir, tempfile.TemporaryDirectory() as target_dir:
            source_root = Path(source_dir)
            target_root = Path(target_dir)
            (source_root / "vnc.html").write_text("<html>noVNC</html>", encoding="utf-8")

            prepared_root = module.prepare_novnc_web_root(source_root, target_root)

            self.assertEqual(prepared_root, target_root)
            self.assertEqual((target_root / "vnc.html").read_text(encoding="utf-8"), "<html>noVNC</html>")
            self.assertEqual((target_root / "health").read_text(encoding="utf-8"), '{"status":"ok"}')

    def test_build_chromium_command_enables_remote_debugging_and_profile_dir(self):
        os.environ["PORT"] = "38080"
        module = importlib.import_module("browser_service")
        config = module.build_browser_service_config()

        command = module.build_chromium_command(config, executable_path="/ms-playwright/chromium/chrome")

        self.assertEqual(command[0], "/ms-playwright/chromium/chrome")
        self.assertIn("--remote-debugging-address=0.0.0.0", command)
        self.assertIn("--remote-debugging-port=9222", command)
        self.assertIn(f"--user-data-dir={config.profile_dir}", command)
        self.assertIn("https://www.jd.com/", command)

    def test_service_launcher_uses_browser_mode_command(self):
        os.environ["FITORNOT_SERVICE_MODE"] = "browser"
        module = importlib.import_module("service_launcher")

        command = module.build_service_command()

        self.assertEqual(command, [sys.executable, "-m", "browser_service"])

    def test_service_launcher_uses_backend_mode_command_with_port(self):
        os.environ["PORT"] = "8123"
        module = importlib.import_module("service_launcher")

        command = module.build_service_command()

        self.assertEqual(
            command,
            [sys.executable, "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8123"],
        )

    def test_browser_service_resolves_playwright_executable_when_env_override_missing(self):
        module = importlib.import_module("browser_service")

        class FakePlaywrightContext:
            def __enter__(self):
                return type(
                    "Playwright",
                    (),
                    {"chromium": type("Chromium", (), {"executable_path": "/ms-playwright/chromium/chrome"})()},
                )()

            def __exit__(self, exc_type, exc, tb):
                return False

        with patch.object(module, "sync_playwright", return_value=FakePlaywrightContext()):
            executable = module.resolve_chromium_executable()

        self.assertEqual(executable, "/ms-playwright/chromium/chrome")
