# FITorNOT Storage State Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 `review-pitfall-checker-v2` 增加一个本地导出工具，把已登录的 FITorNOT 浏览器资料目录导出成 Playwright `storageState`，并生成可直接粘贴到 Railway `FITORNOT_BROWSER_STORAGE_STATE` 的 `base64:` 单行值。

**Architecture:** 将纯格式化/校验逻辑放进一个可测试的辅助模块，把 CLI 和 Playwright profile 读取放进独立导出脚本。导出时先复制本地 profile 到临时目录，再用 Playwright 打开临时副本生成 `storageState`，避免直接碰正在使用的资料目录。

**Tech Stack:** Python 3, unittest, Playwright, pathlib, tempfile, argparse, base64, json

---

## File Map

- Create: `review-pitfall-checker-v2/storage_state_export.py`
  - 纯 Python helper：路径解析、payload 校验、base64 编码、输出文件写入
- Create: `review-pitfall-checker-v2/export_fitornot_storage_state.py`
  - CLI 入口：参数解析、Playwright 导出、终端输出
- Create: `review-pitfall-checker-v2/tests/test_storage_state_export.py`
  - helper 与 CLI 边界测试
- Modify: `review-pitfall-checker-v2/README.md`
  - 增加本地导出到 Railway 的说明
- Modify: `review-pitfall-checker-v2/.env.example`
  - 给 `FITORNOT_BROWSER_STORAGE_STATE` 增加导出脚本提示

## Task 1: Build Pure Export Helpers

**Files:**
- Create: `review-pitfall-checker-v2/storage_state_export.py`
- Test: `review-pitfall-checker-v2/tests/test_storage_state_export.py`

- [ ] **Step 1: Write the failing helper tests**

```python
import base64
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import storage_state_export as module


class StorageStateExportHelpersTest(unittest.TestCase):
    def test_encode_storage_state_for_env_returns_base64_prefixed_value(self):
        payload = {"cookies": [{"name": "sid", "value": "x", "domain": ".jd.com", "path": "/"}], "origins": []}

        encoded = module.encode_storage_state_for_env(payload)

        self.assertTrue(encoded.startswith("base64:"))
        decoded = base64.b64decode(encoded[len("base64:"):]).decode("utf-8")
        self.assertEqual(json.loads(decoded), payload)

    def test_validate_storage_state_rejects_empty_payload(self):
        with self.assertRaisesRegex(ValueError, "must contain at least one cookie or origin"):
            module.validate_storage_state_payload({"cookies": [], "origins": []})

    def test_resolve_profile_dir_uses_fitornot_env_when_present(self):
        with patch.dict("os.environ", {"FITORNOT_BROWSER_PROFILE_DIR": "C:/tmp/fitornot-profile"}, clear=False):
            resolved = module.resolve_profile_dir(None)

        self.assertEqual(resolved, Path("C:/tmp/fitornot-profile"))

    def test_write_storage_state_file_persists_json(self):
        payload = {"cookies": [{"name": "sid", "value": "x", "domain": ".jd.com", "path": "/"}], "origins": []}

        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "storage-state.json"
            written = module.write_storage_state_file(payload, output_path)

            self.assertEqual(written, output_path)
            self.assertEqual(json.loads(output_path.read_text(encoding="utf-8")), payload)
```

- [ ] **Step 2: Run the helper test file to verify it fails**

Run:

```bash
python -m unittest tests.test_storage_state_export.StorageStateExportHelpersTest
```

Expected: `ModuleNotFoundError` or missing attribute failures for `storage_state_export`.

- [ ] **Step 3: Write the minimal helper implementation**

```python
from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Any


def resolve_profile_dir(profile_dir: str | None) -> Path:
    if profile_dir:
        return Path(profile_dir).expanduser().resolve()
    default_profile_dir = Path(__file__).resolve().parent / ".browser-profile"
    return Path(os.getenv("FITORNOT_BROWSER_PROFILE_DIR", default_profile_dir)).expanduser().resolve()


def validate_storage_state_payload(payload: dict[str, Any]) -> dict[str, Any]:
    cookies = payload.get("cookies") or []
    origins = payload.get("origins") or []
    if not isinstance(cookies, list) or not isinstance(origins, list):
        raise ValueError("storageState must include list-shaped cookies and origins.")
    if not cookies and not origins:
        raise ValueError("storageState must contain at least one cookie or origin.")
    return {"cookies": cookies, "origins": origins}


def encode_storage_state_for_env(payload: dict[str, Any]) -> str:
    normalized = validate_storage_state_payload(payload)
    raw = json.dumps(normalized, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return f"base64:{base64.b64encode(raw).decode('ascii')}"


def write_storage_state_file(payload: dict[str, Any], output_path: Path) -> Path:
    normalized = validate_storage_state_payload(payload)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path
```

- [ ] **Step 4: Run the helper tests again**

Run:

```bash
python -m unittest tests.test_storage_state_export.StorageStateExportHelpersTest
```

Expected: `OK`

- [ ] **Step 5: Commit the helper foundation**

```bash
git add review-pitfall-checker-v2/storage_state_export.py review-pitfall-checker-v2/tests/test_storage_state_export.py
git commit -m "feat: add storage state export helpers"
```

## Task 2: Add Playwright Export CLI

**Files:**
- Create: `review-pitfall-checker-v2/export_fitornot_storage_state.py`
- Modify: `review-pitfall-checker-v2/storage_state_export.py`
- Test: `review-pitfall-checker-v2/tests/test_storage_state_export.py`

- [ ] **Step 1: Write failing tests for CLI-facing behavior**

```python
class StorageStateExportCliTest(unittest.TestCase):
    def test_build_export_summary_includes_railway_env_value(self):
        payload = {"cookies": [{"name": "sid", "value": "x", "domain": ".jd.com", "path": "/"}], "origins": []}

        summary = module.build_export_summary(payload, Path("C:/tmp/storage-state.json"))

        self.assertEqual(summary["output_path"], "C:/tmp/storage-state.json")
        self.assertTrue(summary["env_value"].startswith("base64:"))
        self.assertIn("FITORNOT_BROWSER_STORAGE_STATE=", summary["env_assignment"])

    def test_assert_profile_dir_exists_rejects_missing_directory(self):
        with self.assertRaisesRegex(FileNotFoundError, "Profile directory does not exist"):
            module.assert_profile_dir_exists(Path("C:/definitely-missing-fitornot-profile"))
```

- [ ] **Step 2: Run just the CLI-support tests and verify failure**

Run:

```bash
python -m unittest tests.test_storage_state_export.StorageStateExportCliTest
```

Expected: missing `build_export_summary` / `assert_profile_dir_exists`.

- [ ] **Step 3: Extend the helper module with summary and path validation**

```python
def assert_profile_dir_exists(profile_dir: Path) -> Path:
    if not profile_dir.exists():
        raise FileNotFoundError(f"Profile directory does not exist: {profile_dir}")
    if not profile_dir.is_dir():
        raise FileNotFoundError(f"Profile path is not a directory: {profile_dir}")
    return profile_dir


def build_export_summary(payload: dict[str, Any], output_path: Path) -> dict[str, str]:
    env_value = encode_storage_state_for_env(payload)
    return {
        "output_path": str(output_path),
        "env_value": env_value,
        "env_assignment": f"FITORNOT_BROWSER_STORAGE_STATE={env_value}",
    }
```

- [ ] **Step 4: Add the actual CLI script**

```python
from __future__ import annotations

import argparse
import asyncio
import shutil
import sys
import tempfile
from pathlib import Path

from domestic_browser import _default_browser_channel, sync_browser_profile
from storage_state_export import (
    assert_profile_dir_exists,
    build_export_summary,
    resolve_profile_dir,
    validate_storage_state_payload,
    write_storage_state_file,
)


async def export_storage_state(profile_dir: Path, output_path: Path) -> dict[str, str]:
    from playwright.async_api import async_playwright

    assert_profile_dir_exists(profile_dir)
    with tempfile.TemporaryDirectory(prefix="fitornot-storage-state-") as temp_dir:
        temp_profile = Path(temp_dir) / "profile"
        sync_browser_profile(profile_dir, temp_profile)
        async with async_playwright() as playwright:
            context = await playwright.chromium.launch_persistent_context(
                user_data_dir=str(temp_profile),
                headless=True,
                channel=_default_browser_channel(),
            )
            try:
                payload = validate_storage_state_payload(await context.storage_state())
            finally:
                await context.close()

    write_storage_state_file(payload, output_path)
    return build_export_summary(payload, output_path)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export FITorNOT browser storage state for Railway.")
    parser.add_argument("--profile-dir", dest="profile_dir")
    parser.add_argument("--output", dest="output")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    profile_dir = resolve_profile_dir(args.profile_dir)
    output_path = Path(args.output or (Path.cwd() / "tmp_fitornot_storage_state.json")).resolve()
    try:
        summary = asyncio.run(export_storage_state(profile_dir, output_path))
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except ModuleNotFoundError:
        print("Playwright is not installed. Run `pip install -r requirements.txt` first.", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"Unable to export a usable storage state: {exc}", file=sys.stderr)
        return 1

    print("FITorNOT storage state exported.")
    print(f"JSON file: {summary['output_path']}")
    print(summary["env_assignment"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: Run the targeted tests**

Run:

```bash
python -m unittest tests.test_storage_state_export
```

Expected: `OK`

- [ ] **Step 6: Commit the export tool**

```bash
git add review-pitfall-checker-v2/storage_state_export.py review-pitfall-checker-v2/export_fitornot_storage_state.py review-pitfall-checker-v2/tests/test_storage_state_export.py
git commit -m "feat: add storage state export cli"
```

## Task 3: Document the Railway Workflow

**Files:**
- Modify: `review-pitfall-checker-v2/README.md`
- Modify: `review-pitfall-checker-v2/.env.example`
- Test: `review-pitfall-checker-v2/tests/test_deployment_artifacts.py`

- [ ] **Step 1: Write the failing documentation regression tests**

```python
def test_readme_documents_storage_state_export_command_for_railway(self) -> None:
    readme = self.project_root / "README.md"
    readme_text = readme.read_text(encoding="utf-8")

    self.assertIn("export_fitornot_storage_state.py", readme_text)
    self.assertIn("FITORNOT_BROWSER_STORAGE_STATE=", readme_text)


def test_env_example_mentions_local_export_script(self) -> None:
    env_example = self.project_root / ".env.example"
    env_text = env_example.read_text(encoding="utf-8")

    self.assertIn("export_fitornot_storage_state.py", env_text)
```

- [ ] **Step 2: Run the deployment artifact tests and verify failure**

Run:

```bash
python -m unittest tests.test_deployment_artifacts
```

Expected: README / `.env.example` assertions fail.

- [ ] **Step 3: Update README and env example**

```text
README additions:
- 先运行 start_fitornot_browser.ps1 并完成登录
- 关闭浏览器后运行:
  python export_fitornot_storage_state.py --output outputs/fitornot-storage-state.json
- 将终端输出的 FITORNOT_BROWSER_STORAGE_STATE=base64:... 粘贴到 Railway

.env.example addition:
# Generate this value locally with `python export_fitornot_storage_state.py`
FITORNOT_BROWSER_STORAGE_STATE=
```

- [ ] **Step 4: Re-run the deployment artifact tests**

Run:

```bash
python -m unittest tests.test_deployment_artifacts
```

Expected: `OK`

- [ ] **Step 5: Commit the docs pass**

```bash
git add review-pitfall-checker-v2/README.md review-pitfall-checker-v2/.env.example review-pitfall-checker-v2/tests/test_deployment_artifacts.py
git commit -m "docs: add railway storage state export steps"
```

## Task 4: Final Verification

**Files:**
- Verify only

- [ ] **Step 1: Run the backend-focused test suite**

Run:

```bash
python -m unittest discover -s tests
```

Expected: all backend tests pass.

- [ ] **Step 2: Run repo verification**

Run:

```bash
npm.cmd exec pnpm -- test
npm.cmd exec pnpm -- lint
npm.cmd exec pnpm -- typecheck
npm.cmd exec pnpm -- verify
```

Expected:
- `test`: pass
- `typecheck`: pass
- `verify`: pass
- `lint`: no new errors; existing warnings may remain unchanged

- [ ] **Step 3: Commit the verification checkpoint if any follow-up tweaks were needed**

```bash
git add review-pitfall-checker-v2
git commit -m "chore: verify storage state export workflow"
```

## Self-Review

- Spec coverage: helper encoding, CLI export, Railway docs, regression tests, and final verification are all covered.
- Placeholder scan: no `TODO` / `TBD` / vague “add error handling” placeholders remain.
- Type consistency: all tasks use the same helper names: `resolve_profile_dir`, `validate_storage_state_payload`, `encode_storage_state_for_env`, `build_export_summary`, `export_storage_state`.
