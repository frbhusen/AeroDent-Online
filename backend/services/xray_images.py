"""
Lossless X-ray image processing and integrity verification.

Rules (see docs/XRAY_STORAGE.md):

* Pixels are never altered. There is no resizing, no JPEG/WebP re-encoding and no bit-depth
  reduction of the stored image.
* JPEG, WebP and GIF uploads are stored byte-for-byte as uploaded: re-encoding them could
  only lose information or waste space.
* PNG, BMP and single-frame TIFF uploads are re-encoded as maximally compressed PNG **only if**
  decoding that PNG yields exactly the same pixels (mode, size, every value) and it is smaller.
  Otherwise the original bytes are kept.
* Every stored image carries SHA-256 hashes of the stored bytes, of the original upload, and
  of the decoded pixels, so corruption or tampering is detectable later.
"""

import hashlib
import warnings
from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError

ALLOWED_FORMATS = frozenset({"JPEG", "PNG", "WEBP", "GIF", "BMP", "TIFF"})
BROWSER_DISPLAYABLE = frozenset({"JPEG", "PNG", "WEBP", "GIF", "BMP"})
LOSSLESS_CANDIDATES = frozenset({"PNG", "BMP", "TIFF"})
MAX_PIXELS = 100_000_000  # 100 megapixels: far above any dental radiograph
PREVIEW_MAX_SIDE = 4096
EXTENSIONS = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp", "GIF": "gif", "BMP": "bmp", "TIFF": "tif"}
_INTEGER_MODES = frozenset({"I", "I;16", "I;16L", "I;16B", "I;16N"})

Image.MAX_IMAGE_PIXELS = MAX_PIXELS


class XRayImageError(Exception):
    def __init__(self, message, status=422):
        super().__init__(message)
        self.message = message
        self.status = status


def _sha256(data):
    return hashlib.sha256(data).hexdigest()


def _open(content):
    """Opens and fully decodes an image, treating decompression-bomb warnings as errors."""
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        try:
            with Image.open(BytesIO(content)) as probe:
                probe.verify()
            image = Image.open(BytesIO(content))
            image.load()
            return image
        except (Image.DecompressionBombError, Image.DecompressionBombWarning):
            raise XRayImageError("Image dimensions are too large.", 413)
        except (UnidentifiedImageError, OSError, ValueError, SyntaxError, EOFError):
            raise XRayImageError("Uploaded file is not a valid image.")


def _canonical_pixels(image):
    """Bytes that represent the decoded pixel values exactly, independent of file format."""
    if image.mode in _INTEGER_MODES:
        return "I", image.convert("I").tobytes()
    if image.mode in ("P", "PA", "1"):
        return "RGBA", image.convert("RGBA").tobytes()
    return image.mode, image.tobytes()


def pixel_sha256(image):
    mode, raw = _canonical_pixels(image)
    digest = hashlib.sha256(f"{mode}|{image.width}x{image.height}|".encode())
    digest.update(raw)
    return digest.hexdigest()


def _pixels_identical(original, candidate):
    if original.size != candidate.size:
        return False
    return _canonical_pixels(original) == _canonical_pixels(candidate)


def _lossless_png(image):
    """Returns PNG bytes only if they decode to exactly the same pixels; otherwise None."""
    params = {"optimize": True, "compress_level": 9}
    if image.info.get("icc_profile"):
        params["icc_profile"] = image.info["icc_profile"]
    if image.info.get("dpi"):
        params["dpi"] = image.info["dpi"]
    if image.mode == "P" and "transparency" in image.info:
        params["transparency"] = image.info["transparency"]
    try:
        buffer = BytesIO()
        image.save(buffer, format="PNG", **params)
        encoded = buffer.getvalue()
        with Image.open(BytesIO(encoded)) as check:
            check.load()
            if not _pixels_identical(image, check):
                return None
        return encoded
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _preview_png(image):
    """8-bit display rendition for formats browsers cannot render. Never used for download."""
    preview = image
    if preview.mode in _INTEGER_MODES or preview.mode == "F":
        preview = preview.convert("I") if preview.mode != "F" else preview
        low, high = preview.getextrema()
        scale = 255.0 / (high - low) if high > low else 1.0
        preview = preview.point(lambda value: (value - low) * scale).convert("L")
    elif preview.mode not in ("L", "RGB", "RGBA"):
        preview = preview.convert("RGBA" if "A" in preview.getbands() else "RGB")
    if max(preview.size) > PREVIEW_MAX_SIDE:
        preview = ImageOps.contain(preview, (PREVIEW_MAX_SIDE, PREVIEW_MAX_SIDE))
    buffer = BytesIO()
    preview.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def process_upload(content, original_filename=None, original_mime_type=None):
    """Validates an upload and returns the fields for an XRayImage row (never lossy)."""
    if not content:
        raise XRayImageError("An image file is required.", 400)

    image = _open(content)
    image_format = image.format
    if image_format not in ALLOWED_FORMATS:
        raise XRayImageError("Unsupported image format.")
    frames = getattr(image, "n_frames", 1)

    stored_bytes, stored_format, encoding = content, image_format, "original"
    if image_format in LOSSLESS_CANDIDATES and frames == 1:
        png = _lossless_png(image)
        if png is not None and len(png) < len(content):
            stored_bytes, stored_format, encoding = png, "PNG", "png-lossless"

    preview = None
    if stored_format not in BROWSER_DISPLAYABLE:
        if frames > 1:
            image.seek(0)  # multi-page files are stored whole; the preview shows page one
        preview = _preview_png(image)

    return {
        "data": stored_bytes,
        "mime_type": Image.MIME.get(stored_format, "application/octet-stream"),
        "image_format": stored_format,
        "encoding": encoding,
        "size_bytes": len(stored_bytes),
        "sha256": _sha256(stored_bytes),
        "width": image.width,
        "height": image.height,
        "color_mode": image.mode,
        "pixel_sha256": pixel_sha256(image),
        "original_filename": original_filename,
        "original_mime_type": Image.MIME.get(image_format, original_mime_type),
        "original_size_bytes": len(content),
        "original_sha256": _sha256(content),
        "preview_data": preview,
        "preview_mime_type": "image/png" if preview else None,
    }


def verify_bytes(record, data):
    """Cheap integrity check used on every download: size and SHA-256 of the stored bytes."""
    if data is None or len(data) != record.size_bytes:
        return False
    return _sha256(data) == record.sha256


def verify_full(record, data):
    """Deep integrity check: byte hash plus re-decoding and comparing the pixel hash."""
    if not verify_bytes(record, data):
        return False, "stored bytes do not match the recorded SHA-256"
    try:
        image = _open(data)
    except XRayImageError:
        return False, "stored bytes no longer decode as an image"
    if (image.width, image.height) != (record.width, record.height):
        return False, "decoded dimensions differ from the recorded dimensions"
    if pixel_sha256(image) != record.pixel_sha256:
        return False, "decoded pixels differ from the recorded pixel hash"
    return True, "ok"


def download_name(filename, image_format):
    """Filename whose extension matches the bytes actually served."""
    base = (filename or "xray").rsplit(".", 1)[0] or "xray"
    return f"{base}.{EXTENSIONS.get(image_format, 'img')}"
