# X-ray storage

## Where images live

X-ray image bytes are **server-owned data stored in PostgreSQL**, in the `xray_images` table,
one row per X-ray:

* `xray_images.(clinic_id, xray_id)` → `x_rays.(clinic_id, id)` composite foreign key with
  `ON DELETE CASCADE`. An image can only belong to an X-ray of the same clinic, and deleting an
  X-ray (or its patient, or its clinic) deletes the image in the same transaction.
* Upload writes the `x_rays` row and the `xray_images` row in **one transaction**. If anything
  fails (invalid image, constraint, database error) neither row exists. There is no filesystem
  step, so a record can never point at a missing file and no file can be orphaned.
* After a successful upload the browser's copy is irrelevant: deleting the file from the
  computer or phone has no effect. The application never stores or uses a client file path.
* The byte columns use `STORAGE EXTERNAL` (out-of-line, no pglz pass, since image data is
  already compressed) and are `deferred` in SQLAlchemy, so listing X-rays never loads bytes.

Why the database rather than object storage: the requirement is database-backed persistence
with transactional consistency. Dental radiographs are typically 0.1–15 MB; PostgreSQL handles
this comfortably (TOAST, 1 GB per value) and every standard backup (`pg_dump`, base backups,
PITR) now includes the images automatically. If a clinic ever outgrows this, the table layout
(`xray_images` separate from `x_rays`) makes moving bytes to object storage a contained change.

## Lossless handling

Nothing stored is ever lossy, resized, or reduced in bit depth.

| Upload | Stored as | Why |
|---|---|---|
| JPEG, WebP, GIF, multi-page TIFF | **original bytes, unchanged** (`encoding = original`) | Re-encoding could only lose data (JPEG/WebP) or gain nothing. |
| PNG, BMP, single-page TIFF (8/16-bit gray, RGB, RGBA, palette) | **maximally compressed PNG** (`encoding = png-lossless`) — *only if* decoding it gives exactly the same pixels (mode, size, every value, 16-bit preserved) **and** it is smaller | True lossless compression; verified per upload. |
| Anything where the PNG check fails or is not smaller (e.g. CMYK TIFF, already-optimal PNG) | original bytes, unchanged | Preserve rather than degrade. |

Browsers cannot display TIFF. For such originals a clearly separate 8-bit PNG **preview** is
generated for on-screen viewing only (`preview_data`). Downloads (`?download=1`) always return
the stored original / lossless bytes, with a filename extension matching the real format.

The previous pipeline (removed) resized to 1600 px and re-encoded as lossy WebP (quality 82),
both online and in offline mode. Offline mode now stores the selected file exactly as-is.

## Integrity

Each `xray_images` row stores:

* `sha256` – hash of the stored bytes (checked on **every download**; a mismatch returns
  `409`, is logged, and is recorded in the audit log as `xray_integrity_failed`),
* `original_sha256`, `original_size_bytes`, `original_filename`, `original_mime_type` – the
  upload as received,
* `pixel_sha256` – hash of the decoded pixel values; proves a re-encoded PNG is identical to the
  upload and detects corruption that still decodes,
* `width`, `height`, `color_mode`, `image_format`, `mime_type`, `encoding`, `created_at`;
  the `x_rays` row keeps clinic, patient, uploader, date/time and clinical metadata.

Verification:

* `GET /api/x-rays/<id>/verify` – re-hashes and re-decodes one image.
* `flask --app backend.app xrays verify` – checks every stored image; exits non-zero on failure
  (suitable for a nightly job).

## Access control

* All endpoints require a live session, the `xrays.*` permission, and are scoped to the user's
  clinic: another clinic's X-ray is indistinguishable from a non-existent one (`404`).
* Files are served only through `GET /api/x-rays/<id>/file` — never from a public path — with
  `Cache-Control: no-store, private`, `X-Content-Type-Options: nosniff` and a sandboxing
  `Content-Security-Policy`. The content type comes from the decoded image, never from the
  client's filename or MIME header.
* Uploads are size-limited (`AERODENT_XRAY_MAX_MB`, default 25), rate-limited (200 per user per
  hour), fully decoded before acceptance, and protected against decompression bombs
  (100-megapixel cap). Non-images, truncated files, SVG and other active content are rejected.
* Download and upload events are audit-logged without clinical content.

## Backups and export

* **Database backups contain the images.** Back up PostgreSQL as usual; no separate file
  store needs to be backed up for X-rays uploaded after this change.
* `GET /api/clinic/export` lists every X-ray with format, size, dimensions and both hashes, plus
  its download URL, so an export can be checked against the stored images.
* Images uploaded before this change remain on the server filesystem (`x_rays.storage_key`)
  and keep working. Import them once with:

  ```bash
  flask --app backend.app xrays import-legacy            # copy into PostgreSQL
  flask --app backend.app xrays import-legacy --delete-files   # ...and remove the files
  ```

  They are copied byte-for-byte and marked `legacy-webp`, because the old pipeline had already
  reduced them; their original quality cannot be recovered.
