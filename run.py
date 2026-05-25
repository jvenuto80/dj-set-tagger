#!/usr/bin/env python3
"""
SetList Desktop Launcher
Double-click this file or run: python3 run.py

Starts the SetList music organizer as a local desktop app — bootstraps a
Python virtualenv, installs deps, builds the frontend, and runs uvicorn.
"""
import subprocess
import sys
import os
import time
import webbrowser
import signal
import platform

# Configuration
PORT = int(os.environ.get("PORT", 8080))
HOST = "127.0.0.1"
APP_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.join(APP_DIR, "backend")
FRONTEND_DIR = os.path.join(APP_DIR, "frontend")
CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".setlist")
VENV_DIR = os.path.join(CONFIG_DIR, ".venv-setlist")
DB_PATH = os.path.join(CONFIG_DIR, "dj_tagger.db")
IS_NATIVE = os.environ.get("SETLIST_NATIVE") == "1"

processes = []


def log(msg):
    print(f"  → {msg}")


def check_python():
    if sys.version_info < (3, 9):
        print(f"❌ Python 3.9+ required (you have {sys.version})")
        sys.exit(1)
    log(f"Python {sys.version_info.major}.{sys.version_info.minor} ✓")


def check_node():
    try:
        result = subprocess.run(["node", "--version"], capture_output=True, text=True)
        version = result.stdout.strip()
        log(f"Node.js {version} ✓")
    except FileNotFoundError:
        print("❌ Node.js not found. Install from https://nodejs.org/")
        sys.exit(1)


def setup_venv():
    pip = os.path.join(VENV_DIR, "bin", "pip") if platform.system() != "Windows" else os.path.join(VENV_DIR, "Scripts", "pip.exe")
    python = os.path.join(VENV_DIR, "bin", "python") if platform.system() != "Windows" else os.path.join(VENV_DIR, "Scripts", "python.exe")
    
    if not os.path.exists(pip):
        log("Creating virtual environment...")
        subprocess.run([sys.executable, "-m", "venv", VENV_DIR], check=True)
    
    # Check if deps are installed
    result = subprocess.run([pip, "show", "fastapi"], capture_output=True)
    if result.returncode != 0:
        log("Installing Python dependencies...")
        subprocess.run([pip, "install", "-r", os.path.join(BACKEND_DIR, "requirements.txt")], check=True)
    else:
        log("Python dependencies ✓")
    
    return python, pip


def setup_frontend():
    node_modules = os.path.join(FRONTEND_DIR, "node_modules")
    dist = os.path.join(FRONTEND_DIR, "dist")
    
    if not os.path.exists(node_modules):
        log("Installing frontend dependencies...")
        subprocess.run(["npm", "install"], cwd=FRONTEND_DIR, check=True)
    else:
        log("Frontend dependencies ✓")
    
    if not os.path.exists(dist):
        log("Building frontend...")
        subprocess.run(["npm", "run", "build"], cwd=FRONTEND_DIR, check=True)
    else:
        log("Frontend build ✓")


def setup_config():
    os.makedirs(CONFIG_DIR, exist_ok=True)
    log(f"Config directory: {CONFIG_DIR}")


def start_backend(python):
    log(f"Starting SetList on http://{HOST}:{PORT} ...")
    env = os.environ.copy()
    env["MUSIC_DIR"] = os.path.expanduser("~/Music")
    env["CONFIG_DIR"] = CONFIG_DIR
    env["PYTHONPATH"] = APP_DIR
    env["SETLIST_NATIVE"] = "1"
    env["SETLIST_SERVE_FRONTEND"] = os.path.join(FRONTEND_DIR, "dist")

    # Inherit the launcher's process group so a SIGTERM sent to us by Tauri
    # propagates to uvicorn and any of its workers as well.
    proc = subprocess.Popen(
        [python, "-m", "uvicorn", "backend.main:app",
         "--host", HOST, "--port", str(PORT)],
        cwd=APP_DIR,
        env=env,
    )
    processes.append(proc)
    return proc


def wait_for_backend():
    import urllib.request
    for i in range(30):
        try:
            urllib.request.urlopen(f"http://{HOST}:{PORT}/api/health", timeout=1)
            return True
        except Exception:
            time.sleep(0.5)
    return False


def cleanup(*args):
    print("\n  Shutting down...")
    # Best-effort: ask Ollama to unload our model so VRAM/RAM is freed.
    try:
        import urllib.request
        req = urllib.request.Request(
            f"http://{HOST}:{PORT}/api/ai/unload",
            method="POST",
        )
        urllib.request.urlopen(req, timeout=2).read()
    except Exception:
        pass

    for proc in processes:
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                proc.kill()
            except Exception:
                pass
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
    sys.exit(0)


def main():
    print()
    print("  ╔══════════════════════════════╗")
    print("  ║     🎵 SetList Desktop 🎵    ║")
    print("  ╚══════════════════════════════╝")
    print()
    
    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)
    
    os.chdir(APP_DIR)
    
    check_python()
    if not IS_NATIVE:
        check_node()
    setup_config()
    python, pip = setup_venv()
    if not IS_NATIVE:
        setup_frontend()
    
    print()
    start_backend(python)
    
    log("Waiting for backend...")
    if wait_for_backend():
        url = f"http://{HOST}:{PORT}"
        log(f"Ready! Opening {url}")
        print()
        print(f"  ✅ SetList is running at: {url}")
        print(f"  📁 Config: {CONFIG_DIR}")
        print(f"  Press Ctrl+C to stop")
        print()
        if not IS_NATIVE:
            webbrowser.open(url)
    else:
        print("  ❌ Backend failed to start. Check the output above.")
        cleanup()
    
    # Wait for processes
    try:
        for proc in processes:
            proc.wait()
    except KeyboardInterrupt:
        cleanup()


if __name__ == "__main__":
    main()
