from __future__ import annotations

import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

try:  # pragma: no cover - import availability depends on runtime
    from playwright.sync_api import sync_playwright
except Exception:  # pragma: no cover - import availability depends on runtime
    sync_playwright = None


DEFAULT_BROWSER_SERVICE_START_URL = "https://www.jd.com/"
DEFAULT_BROWSER_SERVICE_DISPLAY = ":99"
DEFAULT_BROWSER_SERVICE_SCREEN_SIZE = "1440x1080x24"
DEFAULT_BROWSER_SERVICE_PUBLIC_PORT = 8080
DEFAULT_BROWSER_SERVICE_CDP_PORT = 9222
DEFAULT_BROWSER_SERVICE_CHROMIUM_CDP_PORT = 9223
DEFAULT_BROWSER_SERVICE_VNC_PORT = 5900
DEFAULT_BROWSER_SERVICE_NOVNC_ROOT = "/usr/share/novnc"
DEFAULT_BROWSER_SERVICE_WEB_ROOT = "/tmp/fitornot-browser-web"
DEFAULT_BROWSER_SERVICE_PROFILE_DIR = Path(__file__).resolve().parent / ".browser-profile"


@dataclass(frozen=True)
class BrowserServiceConfig:
    public_port: int
    cdp_port: int
    chromium_cdp_port: int
    vnc_port: int
    display: str
    screen_size: str
    profile_dir: Path
    start_url: str
    novnc_root: Path
    web_root: Path
    locale: str


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def build_browser_service_config() -> BrowserServiceConfig:
    public_port = _env_int("FITORNOT_BROWSER_PUBLIC_PORT", _env_int("PORT", DEFAULT_BROWSER_SERVICE_PUBLIC_PORT))
    profile_dir = Path(
        os.getenv("FITORNOT_BROWSER_PROFILE_DIR", "").strip() or str(DEFAULT_BROWSER_SERVICE_PROFILE_DIR)
    ).expanduser()
    novnc_root = Path(
        os.getenv("FITORNOT_BROWSER_NOVNC_ROOT", "").strip() or DEFAULT_BROWSER_SERVICE_NOVNC_ROOT
    ).expanduser()
    web_root = Path(
        os.getenv("FITORNOT_BROWSER_WEB_ROOT", "").strip() or DEFAULT_BROWSER_SERVICE_WEB_ROOT
    ).expanduser()
    return BrowserServiceConfig(
        public_port=public_port,
        cdp_port=_env_int("FITORNOT_BROWSER_CDP_PORT", DEFAULT_BROWSER_SERVICE_CDP_PORT),
        chromium_cdp_port=_env_int(
            "FITORNOT_BROWSER_CHROMIUM_CDP_PORT", DEFAULT_BROWSER_SERVICE_CHROMIUM_CDP_PORT
        ),
        vnc_port=_env_int("FITORNOT_BROWSER_VNC_PORT", DEFAULT_BROWSER_SERVICE_VNC_PORT),
        display=os.getenv("FITORNOT_BROWSER_DISPLAY", "").strip() or DEFAULT_BROWSER_SERVICE_DISPLAY,
        screen_size=os.getenv("FITORNOT_BROWSER_SCREEN_SIZE", "").strip() or DEFAULT_BROWSER_SERVICE_SCREEN_SIZE,
        profile_dir=profile_dir,
        start_url=os.getenv("FITORNOT_BROWSER_START_URL", "").strip() or DEFAULT_BROWSER_SERVICE_START_URL,
        novnc_root=novnc_root,
        web_root=web_root,
        locale=os.getenv("FITORNOT_BROWSER_LOCALE", "").strip() or "zh-CN",
    )


def prepare_novnc_web_root(source_root: Path | str, target_root: Path | str) -> Path:
    source_path = Path(source_root)
    target_path = Path(target_root)
    if not source_path.exists():
        raise RuntimeError(f"noVNC static assets directory not found: {source_path}")

    target_path.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source_path, target_path, dirs_exist_ok=True)
    (target_path / "health").write_text('{"status":"ok"}', encoding="utf-8")
    return target_path


def resolve_chromium_executable() -> str:
    explicit = os.getenv("FITORNOT_BROWSER_CHROMIUM_EXECUTABLE", "").strip()
    if explicit:
        return explicit
    if sync_playwright is None:
        raise RuntimeError(
            "Playwright sync runtime is unavailable. Install `playwright` and ensure Chromium is present."
        )
    with sync_playwright() as playwright:
        return playwright.chromium.executable_path


def build_chromium_command(config: BrowserServiceConfig, executable_path: str) -> list[str]:
    return [
        executable_path,
        f"--user-data-dir={config.profile_dir}",
        f"--remote-debugging-port={config.chromium_cdp_port}",
        "--remote-debugging-address=127.0.0.1",
        "--remote-allow-origins=*",
        "--no-first-run",
        "--no-default-browser-check",
        "--no-sandbox",
        "--disable-setuid-sandbox",
        "--disable-dev-shm-usage",
        "--disable-gpu",
        "--disable-blink-features=AutomationControlled",
        "--disable-features=Translate,AcceptCHFrame",
        f"--lang={config.locale}",
        "--window-position=0,0",
        "--window-size=1440,1080",
        config.start_url,
    ]


def build_socat_command(config: BrowserServiceConfig) -> list[str]:
    return [
        "socat",
        f"TCP-LISTEN:{config.cdp_port},fork,reuseaddr,bind=0.0.0.0",
        f"TCP:127.0.0.1:{config.chromium_cdp_port}",
    ]


def build_xvfb_command(config: BrowserServiceConfig) -> list[str]:
    return ["Xvfb", config.display, "-screen", "0", config.screen_size, "-ac", "-nolisten", "tcp"]


def build_fluxbox_command() -> list[str]:
    return ["fluxbox", "-display", os.getenv("DISPLAY", DEFAULT_BROWSER_SERVICE_DISPLAY)]


def build_x11vnc_command(config: BrowserServiceConfig) -> list[str]:
    return [
        "x11vnc",
        "-display",
        config.display,
        "-forever",
        "-shared",
        "-rfbport",
        str(config.vnc_port),
        "-nopw",
    ]


def build_websockify_command(config: BrowserServiceConfig) -> list[str]:
    return [
        "websockify",
        "--web",
        str(config.web_root),
        str(config.public_port),
        f"127.0.0.1:{config.vnc_port}",
    ]


def _wait_for_tcp(host: str, port: int, timeout_seconds: float) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(1)
            try:
                sock.connect((host, port))
            except OSError:
                time.sleep(0.25)
                continue
            return
    raise RuntimeError(f"Timed out waiting for TCP listener on {host}:{port}")


def _launch_process(command: list[str], *, env: dict[str, str] | None = None) -> subprocess.Popen[str]:
    return subprocess.Popen(command, env=env or os.environ.copy())


def _terminate_processes(processes: Iterable[subprocess.Popen[str]]) -> None:
    for process in processes:
        if process.poll() is None:
            process.terminate()
    deadline = time.time() + 10
    for process in processes:
        while process.poll() is None and time.time() < deadline:
            time.sleep(0.1)
        if process.poll() is None:
            process.kill()


def run_browser_service(config: BrowserServiceConfig) -> int:
    config.profile_dir.mkdir(parents=True, exist_ok=True)
    prepare_novnc_web_root(config.novnc_root, config.web_root)

    chromium_executable = resolve_chromium_executable()
    display_env = os.environ.copy()
    display_env["DISPLAY"] = config.display

    processes: list[subprocess.Popen[str]] = []

    def _shutdown(_signum: int, _frame: object) -> None:
        _terminate_processes(reversed(processes))
        raise SystemExit(0)

    previous_sigterm = signal.signal(signal.SIGTERM, _shutdown)
    previous_sigint = signal.signal(signal.SIGINT, _shutdown)
    try:
        xvfb_process = _launch_process(build_xvfb_command(config))
        processes.append(xvfb_process)
        time.sleep(1)

        fluxbox_process = _launch_process(build_fluxbox_command(), env=display_env)
        processes.append(fluxbox_process)

        chromium_process = _launch_process(build_chromium_command(config, chromium_executable), env=display_env)
        processes.append(chromium_process)
        _wait_for_tcp("127.0.0.1", config.chromium_cdp_port, timeout_seconds=30)

        socat_process = _launch_process(build_socat_command(config))
        processes.append(socat_process)
        _wait_for_tcp("127.0.0.1", config.cdp_port, timeout_seconds=30)

        x11vnc_process = _launch_process(build_x11vnc_command(config), env=display_env)
        processes.append(x11vnc_process)
        _wait_for_tcp("127.0.0.1", config.vnc_port, timeout_seconds=30)

        websockify_process = _launch_process(build_websockify_command(config))
        processes.append(websockify_process)

        while True:
            chromium_exit_code = chromium_process.poll()
            if chromium_exit_code is not None:
                return chromium_exit_code
            socat_exit_code = socat_process.poll()
            if socat_exit_code is not None:
                return socat_exit_code
            websockify_exit_code = websockify_process.poll()
            if websockify_exit_code is not None:
                return websockify_exit_code
            time.sleep(1)
    finally:
        signal.signal(signal.SIGTERM, previous_sigterm)
        signal.signal(signal.SIGINT, previous_sigint)
        _terminate_processes(reversed(processes))


def main() -> None:
    config = build_browser_service_config()
    print(
        json.dumps(
            {
                "service": "fitornot-browser",
                "public_port": config.public_port,
                "cdp_port": config.cdp_port,
                "chromium_cdp_port": config.chromium_cdp_port,
                "vnc_port": config.vnc_port,
                "profile_dir": str(config.profile_dir),
                "start_url": config.start_url,
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    raise SystemExit(run_browser_service(config))


if __name__ == "__main__":
    main()
