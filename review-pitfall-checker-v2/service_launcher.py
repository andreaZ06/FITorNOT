from __future__ import annotations

import os
import sys


def resolve_service_mode() -> str:
    raw_mode = os.getenv("FITORNOT_SERVICE_MODE", "").strip().lower()
    if raw_mode == "browser":
        return "browser"
    return "backend"


def build_service_command() -> list[str]:
    if resolve_service_mode() == "browser":
        return [sys.executable, "-m", "browser_service"]

    port = os.getenv("PORT", "").strip() or "8000"
    return [sys.executable, "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", port]


def main() -> None:
    command = build_service_command()
    os.execvp(command[0], command)


if __name__ == "__main__":
    main()
