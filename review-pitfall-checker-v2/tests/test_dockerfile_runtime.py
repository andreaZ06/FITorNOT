import unittest
from pathlib import Path


class DockerfileRuntimeTest(unittest.TestCase):
    def test_dockerfile_installs_playwright_chromium_for_server_runtime(self):
        dockerfile_path = Path(__file__).resolve().parents[1] / "Dockerfile"
        dockerfile_text = dockerfile_path.read_text(encoding="utf-8")

        self.assertIn("python -m playwright install --with-deps chromium", dockerfile_text)
