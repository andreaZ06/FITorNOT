from __future__ import annotations

import argparse
import asyncio
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
    print("Paste this into Railway:")
    print(summary["env_assignment"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
