"""The desktop build serves its frontend from memory (standalone/packed_assets.py)."""

import os
import sys
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from flask import Flask

from standalone.packed_assets import PackedAssets, pack_files, unpack_files


def run_packed_asset_tests():
    web = ROOT_DIR / "web"
    files = {
        path.relative_to(web).as_posix(): path.read_bytes()
        for path in web.rglob("*")
        if path.is_file() and "landing page" not in path.parts
    }
    key = os.urandom(32)

    started = time.time()
    blob = pack_files(files, key)
    assert unpack_files(blob, key) == files
    assert time.time() - started < 10, "packing/unpacking must stay fast (start-up time)"
    assert b"function " not in blob[:4096] and b"<html" not in blob[:4096]
    print("PASS: The frontend packs and unpacks losslessly and quickly, and is not stored as plain text.")

    assets = PackedAssets(unpack_files(blob, key))
    app = Flask(__name__)
    with app.test_request_context("/", headers={"Accept-Encoding": "gzip"}):
        index = assets.serve_index()
        assert index.status_code == 200 and index.headers["Cache-Control"] == "no-store"
        assert assets.version in assets.page_html("index.html").decode()
        script = assets.serve_file("js/app.js")
        assert script.status_code == 200 and script.headers["Content-Encoding"] == "gzip"
        assert script.headers["Cache-Control"] == "no-cache"
        assert assets.exists("js/app.js") and not assets.exists("js/missing.js")
        assert not assets.exists("../backend/app.py") and not assets.exists("/etc/passwd")
        worker = assets.serve_service_worker()
        assert assets.version.encode() in worker.get_data() or worker.headers.get("Content-Encoding") == "gzip"
    with app.test_request_context(f"/js/app.js?v={assets.version}"):
        assert assets.serve_file("js/app.js").headers["Cache-Control"].startswith("public, max-age=31536000")
    print("PASS: Packed assets are served from memory with the same caching rules and no path escapes.")

    print("\n==========================================")
    print("ALL PACKED ASSET TESTS PASSED")
    print("==========================================")


if __name__ == "__main__":
    run_packed_asset_tests()
