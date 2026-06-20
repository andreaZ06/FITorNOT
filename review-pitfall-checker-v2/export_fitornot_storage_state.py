from __future__ import annotations

import argparse
import asyncio
import os
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


def get_async_playwright():
    from playwright.async_api import async_playwright

    return async_playwright


def resolve_cdp_url(profile_dir: Path, explicit_cdp_url: str | None = None) -> str | None:
    if explicit_cdp_url and explicit_cdp_url.strip():
        return explicit_cdp_url.strip()

    env_cdp_url = os.getenv("FITORNOT_BROWSER_CDP_URL", "").strip()
    if env_cdp_url:
        return env_cdp_url

    marker_path = profile_dir / "cdp-url.txt"
    if not marker_path.exists():
        return None

    value = marker_path.read_text(encoding="utf-8").replace("\ufeff", "").strip()
    return value or None


async def _export_from_live_cdp_browser(cdp_url: str, output_path: Path) -> dict[str, str]:
    async_playwright = get_async_playwright()
    async with async_playwright() as playwright:
        browser = await playwright.chromium.connect_over_cdp(cdp_url)
        if not browser.contexts:
            raise ValueError("Live FITorNOT browser session has no exportable browser context.")
        payload = validate_storage_state_payload(await browser.contexts[0].storage_state())

    write_storage_state_file(payload, output_path)
    return build_export_summary(payload, output_path)


async def _export_from_copied_profile(profile_dir: Path, output_path: Path) -> dict[str, str]:
    async_playwright = get_async_playwright()
    with tempfile.TemporaryDirectory(prefix="fitornot-storage-state-") as temp_dir:
        temp_profile_dir = Path(temp_dir) / "profile"
        temp_profile_dir.mkdir(parents=True, exist_ok=True)
        sync_browser_profile(profile_dir, temp_profile_dir)

        async with async_playwright() as playwright:
            context = await playwright.chromium.launch_persistent_context(
                user_data_dir=str(temp_profile_dir),
                headless=True,
                channel=_default_browser_channel(),
            )
            try:
                payload = validate_storage_state_payload(await context.storage_state())
            finally:
                await context.close()

    write_storage_state_file(payload, output_path)
    return build_export_summary(payload, output_path)


async def export_storage_state(profile_dir: Path, output_path: Path) -> dict[str, str]:
    assert_profile_dir_exists(profile_dir)
    cdp_url = resolve_cdp_url(profile_dir)

    if cdp_url:
        return await _export_from_live_cdp_browser(cdp_url, output_path)

    return await _export_from_copied_profile(profile_dir, output_path)


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
        print(
            "Tip: start the FITorNOT browser with start_fitornot_browser.ps1, keep it open, and export again.",
            file=sys.stderr,
        )
        return 1

    print("FITorNOT storage state exported.")
    print(f"JSON file: {summary['output_path']}")
    print("Paste this into Railway:")
    print(summary["env_assignment"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
