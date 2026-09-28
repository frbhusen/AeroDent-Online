"""
Static frontend asset delivery with safe caching.

Only public, user-independent files from ``web/`` are cached here. Nothing in this module
ever touches API responses or clinic data.

* Asset version: a SHA-256 over every file in ``web/`` computed once per process. It is
  appended as ``?v=<version>`` to every local script/style/manifest/icon reference in
  ``index.html`` and into ``sw.js``. A deploy that changes any file changes the version, so
  browsers fetch new URLs instead of trusting stale ones (cache busting by content).
* Versioned asset responses are ``public, max-age=1y, immutable``; unversioned requests are
  ``no-cache`` (always revalidated with ETag / Last-Modified).
* ``index.html`` is ``no-store``: it is the shell of a page that holds private data in memory,
  and ``no-store`` keeps browsers from restoring a logged-in page from the back/forward cache
  after logout. ``sw.js`` is ``no-cache`` so service-worker updates are picked up promptly.
* Gzip: text assets are gzip-compressed once and kept in an in-process cache keyed by
  (path, mtime, size), so a changed file on disk is recompressed automatically.
"""

import gzip
import hashlib
import mimetypes
import os
import re
import threading

from flask import Response, request, send_from_directory

IMMUTABLE_CACHE = "public, max-age=31536000, immutable"
REVALIDATE_CACHE = "no-cache"
NO_STORE = "no-store"

_COMPRESSIBLE_EXTENSIONS = frozenset({".js", ".css", ".html", ".json", ".svg", ".ico", ".txt"})
_MIN_GZIP_BYTES = 1024
_LOCAL_REF = re.compile(
    r'(?P<attr>\b(?:src|href))="(?P<path>(?!https?:|//|data:|#|mailto:)[^"?#]+\.(?:js|css|json|png|ico|svg|webmanifest))"'
)
# The public landing page lives in ``web/landing page/`` and references its assets with
# RELATIVE paths (so it can also be hosted standalone). When we serve it as the site root
# ("/"), those relative paths would resolve against "/" and collide with the app's own
# ``/styles.css`` / ``/i18n.js``. This rewrites every relative src/href to an absolute
# ``/landing page/…`` path. Absolute (/…), external (http(s):, //), anchors (#…), and
# mailto:/tel:/data: references are left untouched.
_LANDING_DIR = "landing page"
_LANDING_REF = re.compile(
    r'(?P<attr>\b(?:src|href))="(?P<path>(?!https?:|//|/|#|mailto:|tel:|data:)[^"]+)"'
)


class StaticAssets:
    def __init__(self, web_dir):
        self.web_dir = os.path.abspath(web_dir)
        self._lock = threading.Lock()
        self._gzip_cache = {}
        self.version = self._compute_version()
        self._pages = {}
        self._service_worker = None

    # ------------------------------------------------------------------ version
    def _compute_version(self):
        digest = hashlib.sha256()
        for root, dirs, files in os.walk(self.web_dir):
            dirs.sort()
            for name in sorted(files):
                path = os.path.join(root, name)
                digest.update(os.path.relpath(path, self.web_dir).encode())
                with open(path, "rb") as handle:
                    digest.update(handle.read())
        return digest.hexdigest()[:12]

    # ------------------------------------------------------------------ documents
    def page_html(self, name):
        """HTML document with every local asset reference pinned to the current version."""
        if name not in self._pages:
            with open(os.path.join(self.web_dir, name), encoding="utf-8") as handle:
                html = handle.read()
            html = _LOCAL_REF.sub(
                lambda m: f'{m.group("attr")}="{m.group("path")}?v={self.version}"', html
            )
            html = html.replace("</head>", f'    <meta name="aerodent-asset-version" content="{self.version}">\n</head>', 1)
            self._pages[name] = html.encode("utf-8")
        return self._pages[name]

    def index_html(self):
        return self.page_html("index.html")

    def landing_home_html(self):
        """The public landing page, served as the site root with asset paths made absolute."""
        if "__landing_home__" not in self._pages:
            path = os.path.join(self.web_dir, _LANDING_DIR, "index.html")
            with open(path, encoding="utf-8") as handle:
                html = handle.read()
            html = _LANDING_REF.sub(
                lambda m: f'{m.group("attr")}="/{_LANDING_DIR}/{m.group("path")}"', html
            )
            self._pages["__landing_home__"] = html.encode("utf-8")
        return self._pages["__landing_home__"]

    def service_worker(self):
        if self._service_worker is None:
            with open(os.path.join(self.web_dir, "sw.js"), encoding="utf-8") as handle:
                self._service_worker = handle.read().replace("__ASSET_VERSION__", self.version).encode("utf-8")
        return self._service_worker

    # ------------------------------------------------------------------ gzip
    def _accepts_gzip(self):
        return "gzip" in (request.headers.get("Accept-Encoding") or "").lower()

    def _gzipped(self, key, payload):
        cached = self._gzip_cache.get(key)
        if cached is not None:
            return cached
        compressed = gzip.compress(payload, compresslevel=6, mtime=0)
        with self._lock:
            self._gzip_cache[key] = compressed
        return compressed

    def _bytes_response(self, payload, mimetype, cache_control, cache_key):
        body = payload
        headers = {"Cache-Control": cache_control, "Vary": "Accept-Encoding"}
        if len(payload) >= _MIN_GZIP_BYTES and self._accepts_gzip():
            body = self._gzipped(cache_key, payload)
            headers["Content-Encoding"] = "gzip"
        response = Response(body, mimetype=mimetype, headers=headers)
        return response

    # ------------------------------------------------------------------ serving
    def serve_page(self, name):
        return self._bytes_response(
            self.page_html(name), "text/html", NO_STORE, ("__page__", name, self.version)
        )

    def serve_index(self):
        return self.serve_page("index.html")

    def serve_landing_home(self):
        return self._bytes_response(
            self.landing_home_html(), "text/html", REVALIDATE_CACHE, ("__landing_home__", self.version)
        )

    def serve_service_worker(self):
        response = self._bytes_response(
            self.service_worker(), "application/javascript", REVALIDATE_CACHE, ("__sw__", self.version)
        )
        response.headers["Service-Worker-Allowed"] = "/"
        return response

    def serve_file(self, relative_path):
        full_path = os.path.join(self.web_dir, relative_path)
        cache_control = IMMUTABLE_CACHE if request.args.get("v") == self.version else REVALIDATE_CACHE
        extension = os.path.splitext(relative_path)[1].lower()

        if extension in _COMPRESSIBLE_EXTENSIONS and self._accepts_gzip():
            stat = os.stat(full_path)
            if stat.st_size >= _MIN_GZIP_BYTES:
                with open(full_path, "rb") as handle:
                    payload = handle.read()
                mimetype = mimetypes.guess_type(full_path)[0] or "application/octet-stream"
                response = self._bytes_response(
                    payload, mimetype, cache_control, (relative_path, stat.st_mtime_ns, stat.st_size)
                )
                response.set_etag(f"{self.version}-{stat.st_mtime_ns}-{stat.st_size}-gz")
                return response.make_conditional(request)

        response = send_from_directory(self.web_dir, relative_path)
        response.headers["Cache-Control"] = cache_control
        response.headers["Vary"] = "Accept-Encoding"
        return response
