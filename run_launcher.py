"""
Launcher for Windows (double-clickable)
- Verifies/installs Python requirements (backend/requirements.txt)
- Runs frontend (npm) and backend (uvicorn) processes
- Opens the frontend in the default browser

Notes:
- Node.js (npm) must be available in PATH to auto-install frontend deps.
- MT5 desktop must be running and logged in for the backend to connect to it.
"""

import sys
import subprocess
import os
import shutil
import time
import webbrowser
from pathlib import Path

def _determine_root():
    # Determine the project root when running as a script or as a bundled executable.
    # If frozen (PyInstaller), start from the executable location; otherwise from the script file.
    if getattr(sys, "frozen", False):
        start = Path(sys.executable).resolve().parent
    else:
        start = Path(__file__).resolve().parent

    p = start
    # Walk up a few levels to find a folder that contains the backend directory
    for _ in range(10):
        if (p / "backend").exists() and (p / "package.json").exists():
            return p
        if (p / "backend").exists():
            return p
        p = p.parent

    # If this exe lives in a 'dist' directory next to the project, try its parent
    if start.name == "dist" and start.parent.exists():
        return start.parent

    # Fallback to start
    return start

ROOT = _determine_root()
BACKEND_DIR = ROOT / "backend"
REQ_FILE = BACKEND_DIR / "requirements.txt"
# fallback to combined full requirements if the standard file is missing
REQ_FULL = BACKEND_DIR / "requirements_full.txt"

FRONTEND_DIR = ROOT
FRONTEND_URL = "http://localhost:5173"
BACKEND_URL = "http://localhost:8002"

PY = sys.executable
PIP = [PY, "-m", "pip"]


def run(cmd, cwd=None, check=False, shell=False, env=None):
    return subprocess.run(cmd, cwd=cwd, check=check, shell=shell, env=env)


def ensure_python_version():
    v = sys.version_info
    if v.major < 3 or (v.major == 3 and v.minor < 12):
        msg = f"Python 3.12+ is required. Current: {v.major}.{v.minor}\nPlease install Python 3.12 and try again."
        print(msg)
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, msg, "Python version error", 0)
        except Exception:
            pass
        sys.exit(1)


def install_python_requirements():
    # Prefer backend/requirements.txt, fall back to requirements_full.txt
    req = REQ_FILE if REQ_FILE.exists() else (REQ_FULL if REQ_FULL.exists() else None)
    if not req:
        print("No requirements file found in backend/. Please ensure backend/requirements.txt exists.")
        return False

    print(f"Checking Python requirements from {req}...")

    # Try to compare installed packages and only install missing/out-of-range ones.
    try:
        freeze = subprocess.check_output(PIP + ["freeze"], text=True)
        installed = {}
        for line in freeze.splitlines():
            if "==" in line:
                n, v = line.split("==", 1)
                installed[n.lower()] = v
    except Exception:
        installed = {}

    to_install = []
    try:
        from packaging.specifiers import SpecifierSet
        from packaging.version import Version
        import re
        for raw in open(req, 'r', encoding='utf-8'):
            line = raw.strip()
            if not line or line.startswith('#'):
                continue
            # remove env markers after ';'
            line = line.split(';', 1)[0].strip()
            # strip inline comments
            if '#' in line:
                line = line.split('#', 1)[0].strip()
            if not line:
                continue
            # find first operator to split name / spec
            m = re.search(r'(==|~=|>=|<=|>|<)', line)
            if m:
                name = line[:m.start()].strip()
                spec = line[m.start():].strip()
            else:
                name = line
                spec = ''
            # strip extras like pkg[extra]
            name = re.sub(r'\[.*\]', '', name)
            lname = name.lower()
            if lname in installed:
                if spec:
                    try:
                        specset = SpecifierSet(spec)
                        if Version(installed[lname]) in specset:
                            continue
                        else:
                            to_install.append(line)
                    except Exception:
                        to_install.append(line)
                else:
                    # installed and no spec -> OK
                    continue
            else:
                to_install.append(line)
    except Exception:
        # packaging not available or parsing failed — fall back to full install
        print("Could not evaluate installed packages precisely; running full pip install -r.")
        cmd = PIP + ["install", "-r", str(req)]
        proc = subprocess.run(cmd)
        return proc.returncode == 0

    if not to_install:
        print("All python requirements satisfied. No install needed.")
        return True

    print("Installing missing/updated packages: " + ", ".join(to_install))
    cmd = PIP + ["install"] + to_install
    proc = subprocess.run(cmd)
    return proc.returncode == 0


def ensure_node_and_install_frontend():
    npm = shutil.which("npm")
    if not npm:
        msg = (
            "Node.js (npm) is not available in PATH. The launcher can\'t auto-install frontend dependencies.\n"
            "Please install Node.js from https://nodejs.org/ then re-run the launcher."
        )
        print(msg)
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, msg, "Node.js missing", 0)
        except Exception:
            pass
        return False

    # Install frontend dependencies
    print("Installing frontend (npm) dependencies...")
    proc = subprocess.run([npm, "install"], cwd=str(FRONTEND_DIR))
    return proc.returncode == 0


def start_backend():
    # Uses uvicorn installed in the backend environment
    # Run without --reload (single-process) for launcher stability
    print("Starting backend (uvicorn)...")
    cmd = [PY, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", "8002"]
    # Run in new console window so logs are visible to the user
    CREATE_NEW = 0x00000010
    try:
        # Start detached so the launcher can continue
        p = subprocess.Popen(cmd, cwd=str(BACKEND_DIR), creationflags=CREATE_NEW)
        return p
    except Exception:
        # Fallback: start normally
        p = subprocess.Popen(cmd, cwd=str(BACKEND_DIR))
        return p


def start_frontend():
    # Start vite dev server
    print("Starting frontend (npm run dev)...")
    npm = shutil.which("npm")
    if not npm:
        return None
    CREATE_NEW = 0x00000010
    try:
        p = subprocess.Popen([npm, "run", "dev"], cwd=str(FRONTEND_DIR), creationflags=CREATE_NEW)
        return p
    except Exception:
        p = subprocess.Popen([npm, "run", "dev"], cwd=str(FRONTEND_DIR))
        return p


def open_browser_when_ready(url, timeout=30):
    start = time.time()
    while time.time() - start < timeout:
        try:
            import urllib.request
            with urllib.request.urlopen(url, timeout=2) as r:
                if r.status == 200 or r.status == 403 or r.status == 302:
                    webbrowser.open(url)
                    print(f"Opened browser at {url}")
                    return True
        except Exception:
            pass
        time.sleep(1)
    print(f"Timed out waiting for {url}")
    return False


def main():
    import traceback
    log_path = ROOT / "run_launcher.log"
    try:
        ensure_python_version()

        ok = install_python_requirements()
        if not ok:
            print("Failed to install Python requirements. See console for details.")
            with open(log_path, 'a', encoding='utf-8') as lf:
                lf.write("[ERROR] Python requirements installation failed\n")

        frontend_ok = ensure_node_and_install_frontend()
        if not frontend_ok:
            print("Frontend dependencies not installed. The launcher will still try to start the backend.")
            with open(log_path, 'a', encoding='utf-8') as lf:
                lf.write("[WARN] Frontend dependencies not installed or npm missing\n")

        backend_proc = start_backend()
        # Give backend a moment to start
        time.sleep(2)

        frontend_proc = None
        if frontend_ok:
            frontend_proc = start_frontend()

        # Try opening the frontend; if not available open backend docs
        if not open_browser_when_ready(FRONTEND_URL, timeout=20):
            open_browser_when_ready(BACKEND_URL + "/docs", timeout=20)

        print("Launcher started. Close this window to exit the launcher; backend/frontend continue running in their own console windows.")
        with open(log_path, 'a', encoding='utf-8') as lf:
            lf.write("[INFO] Launcher started successfully\n")

    except Exception as e:
        tb = traceback.format_exc()
        print("Launcher encountered an error:")
        print(tb)
        try:
            with open(log_path, 'a', encoding='utf-8') as lf:
                lf.write("[EXCEPTION] " + tb + "\n")
        except Exception:
            pass
        # Show a message box if available so the user notices the error
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, "Launcher error occurred. See run_launcher.log in the project folder.", "Launcher Error", 0)
        except Exception:
            pass
    finally:
        # Keep the console open so the user can read any errors when double-clicking
        try:
            input("\nPress Enter to exit...")
        except Exception:
            # If stdin is not interactive (unlikely), sleep briefly then exit
            time.sleep(5)


if __name__ == '__main__':
    main()
