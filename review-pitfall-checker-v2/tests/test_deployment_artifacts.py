import json
from pathlib import Path
import subprocess
import unittest


class DeploymentArtifactsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.project_root = Path(__file__).resolve().parents[1]
        self.repo_root = Path(__file__).resolve().parents[2]

    def test_required_railway_artifacts_exist_and_include_expected_runtime_settings(self) -> None:
        dockerfile = self.project_root / "Dockerfile"
        dockerignore = self.project_root / ".dockerignore"
        env_example = self.project_root / ".env.example"
        railway_config = self.project_root / "railway.json"

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

        dockerfile_text = dockerfile.read_text(encoding="utf-8")
        dockerignore_text = dockerignore.read_text(encoding="utf-8")
        env_example_text = env_example.read_text(encoding="utf-8")
        railway_payload = json.loads(railway_config.read_text(encoding="utf-8"))

        self.assertIn("uvicorn main:app", dockerfile_text)
        self.assertIn("${PORT:-8000}", dockerfile_text)
        self.assertIn(".browser-profile/", dockerignore_text)
        self.assertIn("DEEPSEEK_API_KEY", env_example_text)
        self.assertIn("BRIGHTDATA_API_KEY", env_example_text)
        self.assertIn("NEON_DATABASE_URL", env_example_text)
        self.assertEqual("/health", railway_payload["deploy"]["healthcheckPath"])

    def test_repo_gitignore_excludes_local_browser_profiles_and_debug_artifacts(self) -> None:
        gitignore = self.repo_root / ".gitignore"
        self.assertTrue(gitignore.exists(), "Repo .gitignore should exist for Railway upload filtering.")

        gitignore_text = gitignore.read_text(encoding="utf-8")

        self.assertIn("review-pitfall-checker-v2/.browser-profile*", gitignore_text)
        self.assertIn("review-pitfall-checker-v2/chrome*.log", gitignore_text)
        self.assertIn("review-pitfall-checker-v2/tmp_*", gitignore_text)

    def test_repo_gitignore_keeps_required_backend_python_modules_uploadable(self) -> None:
        required_paths = [
            "review-pitfall-checker-v2/main.py",
            "review-pitfall-checker-v2/data_cleaning.py",
            "review-pitfall-checker-v2/domestic_browser.py",
            "review-pitfall-checker-v2/requirements.txt",
            "review-pitfall-checker-v2/Dockerfile",
        ]

        for path in required_paths:
            result = subprocess.run(
                ["git", "check-ignore", "--no-index", path],
                cwd=self.repo_root,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertNotEqual(
                result.returncode,
                0,
                f"{path} should not be ignored by repo-level gitignore patterns.",
            )


if __name__ == "__main__":
    unittest.main()
