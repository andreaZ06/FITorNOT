import unittest
from pathlib import Path


class DockerfileRuntimeTest(unittest.TestCase):
    def test_dockerfile_installs_playwright_chromium_for_server_runtime(self):
        dockerfile_path = Path(__file__).resolve().parents[1] / "Dockerfile"
        dockerfile_text = dockerfile_path.read_text(encoding="utf-8")

        self.assertIn("python -m playwright install --with-deps chromium", dockerfile_text)

    def test_dockerfile_installs_browser_service_packages_for_remote_vnc_runtime(self):
        dockerfile_path = Path(__file__).resolve().parents[1] / "Dockerfile"
        dockerfile_text = dockerfile_path.read_text(encoding="utf-8")

        self.assertIn("xvfb", dockerfile_text)
        self.assertIn("x11vnc", dockerfile_text)
        self.assertIn("fluxbox", dockerfile_text)
        self.assertIn("novnc", dockerfile_text)
        self.assertIn("websockify", dockerfile_text)
        self.assertIn("socat", dockerfile_text)

    def test_dockerfile_uses_service_launcher_entrypoint(self):
        dockerfile_path = Path(__file__).resolve().parents[1] / "Dockerfile"
        dockerfile_text = dockerfile_path.read_text(encoding="utf-8")

        self.assertIn("service_launcher.py", dockerfile_text)
