from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import tempfile
from pathlib import Path

from domestic_browser import (
    build_browser_session_config,
    build_persistent_launch_options,
    compact_seed_storage_state,
    encode_seed_storage_state_payload,
    sync_browser_profile,
)

TARGET_URLS = (
    "https://www.jd.com/",
    "https://www.taobao.com/",
    "https://www.xiaohongshu.com/",
)


async def export_seed_storage_state(profile_dir: Path, output_path: Path) -> dict[str, object]:
    from playwright.async_api import async_playwright

    session_config = build_browser_session_config()
    with tempfile.TemporaryDirectory(prefix="fitornot-seed-") as temp_dir:
        temp_profile_dir = Path(temp_dir) / "profile"
        sync_browser_profile(profile_dir, temp_profile_dir)

        async with async_playwright() as playwright:
            context = await playwright.chromium.launch_persistent_context(
                **build_persistent_launch_options(
                    profile_dir=temp_profile_dir,
                    headless=True,
                    session_config=session_config,
                ),
            )
            try:
                page = context.pages[0] if context.pages else await context.new_page()
                for url in TARGET_URLS:
                    with contextlib.suppress(Exception):
                        await page.goto(url, wait_until="domcontentloaded", timeout=15000)
                        await asyncio.sleep(0.5)
                raw_state = await context.storage_state()
            finally:
                await context.close()

    compacted_state = compact_seed_storage_state(raw_state)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(compacted_state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return {
        "output_path": str(output_path),
        "storage_state": compacted_state,
        "encoded": encode_seed_storage_state_payload(compacted_state),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export a compact FITorNOT storage-state payload from a local logged-in browser profile."
    )
    parser.add_argument(
        "--profile-dir",
        default=str(Path(__file__).resolve().parent / ".browser-profile"),
        help="Path to the local FITorNOT browser profile directory.",
    )
    parser.add_argument(
        "--output",
        default="",
        help="Path to write the compact seed storage-state JSON file.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    profile_dir = Path(args.profile_dir).expanduser().resolve()
    if not profile_dir.exists():
        raise SystemExit(f"Profile directory not found: {profile_dir}")

    output_path = (
        Path(args.output).expanduser().resolve()
        if args.output
        else profile_dir / "seed-storage-state.json"
    )
    result = asyncio.run(export_seed_storage_state(profile_dir, output_path))
    storage_state = result["storage_state"]
    encoded = str(result["encoded"])

    print(f"Saved seed storage state to: {result['output_path']}")
    print(
        "Retained cookies/origins: "
        f"{len(storage_state['cookies'])} cookies, {len(storage_state['origins'])} origins"
    )
    print(f"Encoded length: {len(encoded)}")
    print(f"FITORNOT_BROWSER_STORAGE_STATE={encoded}")


if __name__ == "__main__":
    main()
