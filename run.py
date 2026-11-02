#!/usr/bin/env python3
"""One-command launcher for Windows, macOS and Linux (standard library only).

First run: creates backend/.venv and installs the Python packages (needs internet).
Every run: regenerates the dated demo documents, then serves the API and the prebuilt UI
on http://localhost:8000 and opens it in the browser.

    python run.py                 start the app
    python run.py --port 8010     use another port
    python run.py --no-browser    do not open a browser tab
    python run.py --test          run the backend test suite instead
"""
from __future__ import annotations

import argparse
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import venv
import webbrowser
from pathlib import Path
from typing import Dict, List, Optional

MIN_PYTHON = (3, 9)
ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
VENV_DIR = BACKEND / ".venv"
REQUIREMENTS = BACKEND / "requirements.txt"
STAMP = VENV_DIR / "requirements.installed"
IS_WINDOWS = os.name == "nt"


class LaunchError(Exception):
    pass


def step(message: str) -> None:
    print(f"==> {message}", flush=True)


def venv_python() -> Path:
    return VENV_DIR / ("Scripts/python.exe" if IS_WINDOWS else "bin/python")


def child_env() -> Dict[str, str]:
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env.pop("PYTHONHOME", None)
    return env


def run(cmd: List[str], cwd: Path, what: str) -> None:
    if subprocess.call(cmd, cwd=str(cwd), env=child_env()) != 0:
        raise LaunchError(f"{what} failed (see the messages above).")


def venv_works(python: Path) -> bool:
    if not python.exists():
        return False
    try:
        return subprocess.call([str(python), "-c", "import sys"], env=child_env(),
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0
    except OSError:
        return False


def ensure_venv() -> Path:
    python = venv_python()
    if venv_works(python):
        return python
    if VENV_DIR.exists():
        step("The existing virtual environment does not work on this machine; recreating it")
        shutil.rmtree(VENV_DIR, ignore_errors=True)
    step(f"Creating a Python {sys.version.split()[0]} virtual environment in backend/.venv")
    try:
        venv.EnvBuilder(with_pip=True, clear=True).create(str(VENV_DIR))
    except Exception as exc:  # ensurepip missing, permissions, antivirus...
        raise LaunchError(f"Could not create the virtual environment: {exc}") from exc
    if not venv_works(python):
        raise LaunchError("The virtual environment was created but its Python does not start.")
    return python


def ensure_packages(python: Path) -> None:
    wanted = REQUIREMENTS.read_text(encoding="utf-8")
    if STAMP.exists() and STAMP.read_text(encoding="utf-8") == wanted:
        return
    step("Installing Python packages (first run only, needs internet; about a minute)")
    run([str(python), "-m", "pip", "install", "--disable-pip-version-check", "--only-binary", ":all:",
         "-q", "-r", str(REQUIREMENTS)], BACKEND, "Installing Python packages")
    STAMP.write_text(wanted, encoding="utf-8")


def ensure_ui() -> None:
    if (FRONTEND / "dist" / "index.html").exists():
        return
    npm = shutil.which("npm")
    if not npm:
        raise LaunchError("The built UI (frontend/dist) is missing and Node.js is not installed to rebuild it.")
    step("Building the UI with npm")
    if not (FRONTEND / "node_modules").exists():
        run([npm, "install", "--no-audit", "--no-fund"], FRONTEND, "npm install")
    run([npm, "run", "build"], FRONTEND, "Building the UI")


def port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def local_get(url: str) -> bool:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # corporate proxies must not see localhost
    try:
        with opener.open(url, timeout=2) as resp:
            return resp.status == 200
    except Exception:
        return False


def open_browser_when_ready(url: str) -> None:
    deadline = time.time() + 90
    while time.time() < deadline:
        if local_get(f"{url}/api/health"):
            webbrowser.open(url)
            return
        time.sleep(0.5)


def dotenv_defines(key: str) -> bool:
    path = ROOT / ".env"
    if not path.exists():
        return False
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if line.strip().startswith(f"{key}="):
            return True
    return False


def ensure_port_free(port: int) -> None:
    url = f"http://localhost:{port}"
    if port_in_use(port):
        if local_get(f"{url}/api/health"):
            raise LaunchError(f"VendorGate already seems to be running: open {url} (or stop the other window first).")
        raise LaunchError(f"Port {port} is used by another program. Try: start.bat --port 8010")


def serve(python: Path, port: int, open_browser: bool) -> int:
    url = f"http://localhost:{port}"
    env = child_env()
    if port != 8000 and "VO_PUBLIC_BASE_URL" not in env and not dotenv_defines("VO_PUBLIC_BASE_URL"):
        env["VO_PUBLIC_BASE_URL"] = url  # links inside the demo emails
    if open_browser:
        threading.Thread(target=open_browser_when_ready, args=(url,), daemon=True).start()
    print("", flush=True)
    step(f"VendorGate is starting at {url}   (press Ctrl+C to stop)")
    proc = subprocess.Popen([str(python), "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1",
                             "--port", str(port)], cwd=str(BACKEND), env=env)
    try:
        return proc.wait()
    except KeyboardInterrupt:
        # The console delivers Ctrl+C to uvicorn as well; give it time to shut down cleanly.
        try:
            proc.wait(timeout=10)
        except (subprocess.TimeoutExpired, KeyboardInterrupt):
            proc.terminate()
            proc.wait()
        return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Start the VendorGate vendor onboarding demo.")
    env_port = os.environ.get("PORT", "8000").strip()
    parser.add_argument("--port", type=int, default=int(env_port) if env_port.isdigit() else 8000)
    parser.add_argument("--no-browser", action="store_true", help="do not open a browser tab")
    parser.add_argument("--test", action="store_true", help="run the backend test suite and exit")
    args = parser.parse_args(argv)

    if sys.version_info < MIN_PYTHON:
        raise LaunchError(f"Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]} or newer is required "
                          f"(this is {sys.version.split()[0]}).")
    if not (BACKEND / "app" / "main.py").exists():
        raise LaunchError("backend/app is missing. Extract the whole zip first, then run this from the extracted folder.")
    if not 1 <= args.port <= 65535:
        raise LaunchError(f"--port must be between 1 and 65535 (got {args.port}).")
    if not args.test:
        ensure_port_free(args.port)

    python = ensure_venv()
    ensure_packages(python)
    if args.test:
        step("Running the backend test suite")
        return subprocess.call([str(python), "-m", "pytest", "-q", "-p", "no:cacheprovider"],
                               cwd=str(BACKEND), env=child_env())
    step("Generating the demo scenario documents")
    run([str(python), "-m", "scripts.generate_samples"], BACKEND, "Generating demo documents")
    ensure_ui()
    return serve(python, args.port, open_browser=not args.no_browser)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except LaunchError as err:
        print(f"\nERROR: {err}", file=sys.stderr, flush=True)
        sys.exit(1)
    except KeyboardInterrupt:
        sys.exit(130)
