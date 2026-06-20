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
