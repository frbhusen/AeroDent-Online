"""The desktop build's frontend, served from memory.

A normal checkout serves ``web/`` from disk (backend/services/static_assets.py). The packaged
program has no ``web`` folder: ``standalone.build`` packs the (minified and obfuscated) frontend
into one blob that is compiled into the executable (``standalone/_frontend_blob.py`` is generated
at build time and is not in the repository). This module unpacks it into memory at start-up.

The blob is compressed and scrambled with a per-build key. That keeps the files from appearing
in plain text inside the program; it is obfuscation, not cryptography - a program that has to run
on the user's machine can always be inspected by someone determined enough.
"""

import hashlib
import io
import mimetypes
import posixpath
import zipfile

from flask import Response, abort, request

from backend.services.static_assets import (
    IMMUTABLE_CACHE,
    REVALIDATE_CACHE,
    StaticAssets,
    _COMPRESSIBLE_EXTENSIONS,
    _MIN_GZIP_BYTES,
)


def _keystream(key, length):
    blocks = -(-length // 32)  # SHA-256 yields 32 bytes per counter value
    return b"".join(hashlib.sha256(key + counter.to_bytes(8, "big")).digest() for counter in range(blocks))[:length]


def _scramble(data, key):
    """XOR with the key stream. Done as one big-integer operation: a per-byte Python loop took
    over a minute for the multi-megabyte frontend and made the program start far too slowly."""
    if not data:
        return data
    mixed = int.from_bytes(data, "big") ^ int.from_bytes(_keystream(key, len(data)), "big")
    return mixed.to_bytes(len(data), "big")


def pack_files(files, key):
    """{relative path: bytes} -> scrambled zip bytes (used by standalone.build)."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for relative, payload in sorted(files.items()):
            archive.writestr(zipfile.ZipInfo(relative, date_time=(2026, 1, 1, 0, 0, 0)), payload)
    return _scramble(buffer.getvalue(), key)


def unpack_files(blob, key):
    with zipfile.ZipFile(io.BytesIO(_scramble(blob, key))) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


class PackedAssets(StaticAssets):
    def __init__(self, files):
        self._files = files
        super().__init__(web_dir="")  # the version is computed through _iter_files below

    # ------------------------------------------------------------------ file access hooks
    def _iter_files(self):
        for relative in sorted(self._files):
            yield relative, self._files[relative]

    def _clean(self, relative_path):
        path = posixpath.normpath(relative_path.replace("\\", "/"))
        return None if path.startswith(("..", "/")) else path

    def read_bytes(self, relative_path):
        return self._files[self._clean(relative_path)]

    def exists(self, relative_path):
        cleaned = self._clean(relative_path)
        return cleaned is not None and cleaned in self._files

    # ------------------------------------------------------------------ serving
    def serve_file(self, relative_path):
        cleaned = self._clean(relative_path)
        if cleaned is None or cleaned not in self._files:
            abort(404)
        payload = self._files[cleaned]
        cache_control = IMMUTABLE_CACHE if request.args.get("v") == self.version else REVALIDATE_CACHE
        extension = posixpath.splitext(cleaned)[1].lower()
        mimetype = mimetypes.guess_type(cleaned)[0] or "application/octet-stream"
        if extension in _COMPRESSIBLE_EXTENSIONS and len(payload) >= _MIN_GZIP_BYTES and self._accepts_gzip():
            response = self._bytes_response(payload, mimetype, cache_control, (cleaned, self.version))
        else:
            response = Response(payload, mimetype=mimetype)
            response.headers["Cache-Control"] = cache_control
            response.headers["Vary"] = "Accept-Encoding"
        response.set_etag(f"{self.version}-{len(payload)}")
        return response.make_conditional(request)


def load_packed_assets():
    """The assets compiled into this build, or None when running from a plain checkout."""
    try:
        from standalone import _frontend_blob
    except ImportError:
        return None
    return PackedAssets(unpack_files(_frontend_blob.DATA, _frontend_blob.KEY))
