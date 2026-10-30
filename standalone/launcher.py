"""AeroDent desktop edition launcher.

Starts the AeroDent backend on this computer (127.0.0.1 only), keeps all data in one SQLite file in
the user's profile, and opens the app in a native window.

    python -m standalone.launcher              # open the app window
    python -m standalone.launcher --no-window  # just run the local server (development)
    python -m standalone.launcher --check      # start, verify the app answers, then exit

Data lives in %APPDATA%\\AeroDent (override with AERODENT_DATA_DIR): aerodent.db, secret.key,
backups\\ (one automatic copy per day, the last 14 are kept) and aerodent.log.
"""

import argparse
import datetime
import os
import secrets
import socket
import sqlite3
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

APP_NAME = "AeroDent"
PREFERRED_PORT = 48731  # fixed so the window's saved settings (language...) survive restarts
BACKUPS_TO_KEEP = 14


# True in the packaged program: PyInstaller sets sys.frozen, Nuitka defines __compiled__.
PACKAGED = bool(getattr(sys, "frozen", False)) or "__compiled__" in globals()


def data_dir():
    override = os.environ.get("AERODENT_DATA_DIR")
    if override:
        return Path(override)
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / APP_NAME


def configure_environment(directory):
    """Sets the variables the backend reads. Must run before the backend is imported."""
    directory.mkdir(parents=True, exist_ok=True)
    key_file = directory / "secret.key"
    if not key_file.exists():
        key_file.write_text(secrets.token_hex(32), encoding="utf-8")
        try:
            key_file.chmod(0o600)
        except OSError:
            pass  # not supported on every filesystem
    os.environ["AERODENT_EDITION"] = "standalone"
    os.environ["AERODENT_ENV"] = "standalone"
    os.environ["SECRET_KEY"] = key_file.read_text(encoding="utf-8").strip()
    os.environ["DATABASE_URL"] = f"sqlite:///{(directory / 'aerodent.db').as_posix()}"
    os.environ["AERODENT_STORAGE_PATH"] = str(directory / "storage")


def daily_backup(directory):
    """One consistent copy of the database per day; old copies are pruned."""
    database = directory / "aerodent.db"
    if not database.exists():
        return None
    backups = directory / "backups"
    backups.mkdir(exist_ok=True)
    target = backups / f"aerodent-{datetime.date.today():%Y%m%d}.db"
    if not target.exists():
        source = sqlite3.connect(database)
        destination = sqlite3.connect(target)
        with destination:
            source.backup(destination)  # safe even if the file is in use
        destination.close()
        source.close()
    for old in sorted(backups.glob("aerodent-*.db"))[:-BACKUPS_TO_KEEP]:
        old.unlink(missing_ok=True)
    return target


def _port_free(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1) if sys.platform == "win32" else None
        return probe.connect_ex(("127.0.0.1", port)) != 0


def _is_aerodent(port):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/js/edition.js", timeout=2) as response:
            return b"AERODENT_STANDALONE = true" in response.read()
    except OSError:
        return False


def _free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def _wait_until_up(port, timeout=20):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _is_aerodent(port):
            return True
        time.sleep(0.2)
    return False


def _redirect_output(directory):
    """A windowed .exe has no console: keep the log in the data folder instead."""
    if PACKAGED:
        log = open(directory / "aerodent.log", "a", encoding="utf-8", buffering=1)
        sys.stdout = sys.stderr = log


def _find_app_browser():
    """Edge or Chrome, used as a chromeless app window (always present on Windows 10/11)."""
    candidates = []
    if sys.platform == "win32":
        roots = [os.environ.get(name) for name in ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA")]
        for root in filter(None, roots):
            candidates += [
                Path(root) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
                Path(root) / "Google" / "Chrome" / "Application" / "chrome.exe",
            ]
    else:
        import shutil

        candidates = [Path(found) for name in ("google-chrome", "chromium", "chromium-browser", "microsoft-edge")
                      if (found := shutil.which(name))]
    return next((path for path in candidates if path.exists()), None)


def open_window(url, directory):
    """Opens the app in its own window (no tabs or address bar). Blocks until it is closed.

    Uses Edge/Chrome in --app mode with a dedicated profile folder: that keeps the app's settings
    (language, ...) separate from the user's browser and makes the process last exactly as long as
    the window. Falls back to the default browser, in which case the caller keeps serving.
    """
    import subprocess

    browser = _find_app_browser()
    if browser is None:
        webbrowser.open(url)
        return False
    profile = directory / "window-profile"
    subprocess.Popen(
        [
            str(browser),
            f"--app={url}",
            f"--user-data-dir={profile}",
            "--no-first-run",
            "--no-default-browser-check",
            "--window-size=1360,860",
        ]
    ).wait()
    return True


def main(argv=None):
    parser = argparse.ArgumentParser(description="AeroDent desktop edition")
    parser.add_argument("--no-window", action="store_true", help="only run the local server")
    parser.add_argument("--check", action="store_true", help="start, verify the app answers, exit")
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--data-dir", default=None, help="where the database and settings are kept")
    args = parser.parse_args(argv)
    if args.data_dir:
        os.environ["AERODENT_DATA_DIR"] = args.data_dir

    directory = data_dir()
    configure_environment(directory)
    _redirect_output(directory)

    port = args.port or PREFERRED_PORT
    if not _port_free(port):
        if _is_aerodent(port):  # already running: just bring up another window
            if not args.check and not args.no_window:
                open_window(f"http://127.0.0.1:{port}/", directory)
            return 0
        port = _free_port()

    daily_backup(directory)

    from werkzeug.serving import make_server

    from backend.app import app
    from backend.extensions import db
    from standalone.schema import ensure_schema

    with app.app_context():
        added = ensure_schema(db)
        if added:
            print(f"Upgraded the database: added {', '.join(added)}")

    server = make_server("127.0.0.1", port, app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, name="aerodent-server", daemon=True)
    thread.start()
    if not _wait_until_up(port):
        print("The local server did not start.", file=sys.stderr)
        server.shutdown()
        return 1
    url = f"http://127.0.0.1:{port}/"
    print(f"AeroDent is running at {url} (data: {directory})")

    try:
        if args.check:
            return 0
        if args.no_window:
            thread.join()
            return 0
        if not open_window(url, directory):
            thread.join()  # browser fallback: keep serving until the process is stopped
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
