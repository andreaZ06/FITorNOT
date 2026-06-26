import json
from pathlib import Path
import unittest


class DeploymentArtifactsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.project_root = Path(__file__).resolve().parents[1]

    def test_required_railway_artifacts_exist_and_include_expected_runtime_settings(self) -> None:
        dockerfile = self.project_root / "Dockerfile"
        dockerignore = self.project_root / ".dockerignore"
        env_example = self.project_root / ".env.example"
        railway_config = self.project_root / "railway.json"
        browser_railway_config = self.project_root / "railway.browser.json"
        deployment_safe_cleaning_module = self.project_root / "fitornot_cleaning.py"

        self.assertTrue(dockerfile.exists(), "Dockerfile should exist for Railway deployment.")
        self.assertTrue(
            dockerignore.exists(),
            ".dockerignore should exist to keep local state out of the image.",
        )
        self.assertTrue(
            env_example.exists(),
            "A backend-specific .env.example should document Railway environment variables.",
        )
        self.assertTrue(
            railway_config.exists(),
            "railway.json should exist to document deployment health checks.",
        )
        self.assertTrue(
            browser_railway_config.exists(),
            "railway.browser.json should exist for the dedicated browser worker.",
        )
        self.assertTrue(
            deployment_safe_cleaning_module.exists(),
            "A deployment-safe cleaning module should exist outside the root data* ignore pattern.",
        )

        dockerfile_text = dockerfile.read_text(encoding="utf-8")
        dockerignore_text = dockerignore.read_text(encoding="utf-8")
        env_example_text = env_example.read_text(encoding="utf-8")
        railway_payload = json.loads(railway_config.read_text(encoding="utf-8"))
        browser_railway_payload = json.loads(browser_railway_config.read_text(encoding="utf-8"))

        self.assertIn("service_launcher.py", dockerfile_text)
        self.assertIn("socat", dockerfile_text)
        self.assertIn("xvfb", dockerfile_text)
        self.assertIn("websockify", dockerfile_text)
        self.assertIn(".browser-profile/", dockerignore_text)
        self.assertIn("DEEPSEEK_API_KEY", env_example_text)
        self.assertIn("BRIGHTDATA_API_KEY", env_example_text)
        self.assertIn("NEON_DATABASE_URL", env_example_text)
        self.assertIn("FITORNOT_SERVICE_MODE", env_example_text)
        self.assertIn("FITORNOT_BROWSER_CDP_URL", env_example_text)
        self.assertIn("FITORNOT_BROWSER_CHROMIUM_CDP_PORT", env_example_text)
        self.assertEqual("/health", railway_payload["deploy"]["healthcheckPath"])
        self.assertNotIn("healthcheckPath", browser_railway_payload["deploy"])


if __name__ == "__main__":
    unittest.main()
