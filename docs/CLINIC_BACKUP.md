# Clinic backup: export and import

Head doctors can download a complete backup of their clinic and restore a clinic from one
(Settings → Backup). Doctors and secretaries cannot: the server only grants
`clinic_data.export` and `clinic_data.import` to the `head_doctor` role, and the buttons are
hidden for everyone else. Signed-out requests get 401, other roles 403.

## What is in a backup

A backup is one `.zip` file:

| Entry | Contents |
|---|---|
| `manifest.json` | Format name and version, export time, database schema revision, source clinic, who exported it, row counts, and the SHA-256 of every other file. |
| `data.json` | Clinic settings, staff list, the full activity (audit) log, and **every row of every clinic table**: patients, treatments, treatment plans, appointments, waitlist, odontograms, prescriptions and their medications, X-ray records and image metadata, invoices, payments, inventory categories, suppliers, items, batches and movements, staff shifts, time clock entries and staff credentials. |
| `xrays/<id>/data` | Every X-ray image exactly as stored (lossless PNG or the untouched original), stored uncompressed in the ZIP. |
| `xrays/<id>/preview` | The display preview for formats browsers cannot show (e.g. 16-bit TIFF). |
| `legacy_xrays/<id>` | X-rays that were still in the old file storage, as uploaded. |

Never included: password hashes, session data, login throttling data. Staff appear with name,
e-mail, role and active status only.

The table list lives in `backend/services/clinic_backup.py` (`DATA_TABLES`). The test suite fails
if a clinic table is ever added to the database without being added to the backup.

## Import (restore)

Import **replaces all of the clinic's data** with the backup's contents. It requires:

* the head doctor's password (5 wrong attempts lock import for that account, with increasing
  waits), and
* ticking the confirmation box in the UI.

Rules:

* **All or nothing.** The archive is fully validated (structure, checksums, types, references,
  database constraints) and the replacement runs in a single database transaction. If anything
  is wrong, nothing changes and the reason is shown.
* **IDs are never trusted.** Every row gets a new ID and every reference is remapped through
  rows from the same archive. A reference to anything outside the archive is rejected, and any
  `clinic_id` in the file is ignored, so an archive can never touch another clinic.
* **Staff are matched by e-mail** to accounts that already exist in the importing clinic.
  Accounts are never created, changed or deleted by an import. If a person is not found:
  records they authored are attributed to the head doctor doing the import, doctor assignments
  are cleared, and their own HR rows (shifts, time clock, credentials) are skipped. The result
  lists these people so accounts can be created and the backup imported again.
* **The activity log is never overwritten**; the import itself is logged
  (`clinic_data_imported`, or `clinic_import_failed`).
* **X-ray images are verified** against the manifest's SHA-256 before anything is written, so a
  file damaged after export is rejected. An image that was *already* damaged in the database
  when the backup was made is exported as-is, listed in `manifest.json` → `corrupt_images`, and
  restored as-is (the X-ray integrity check keeps reporting it), rather than making the whole
  backup unusable.
  Legacy-storage X-rays in the archive are imported into the database through the normal
  lossless pipeline.
* Clinic settings (name, phone, address, currency, working hours, slot length, inventory expiry
  warning) are restored. Subscription status is not.

Importing a backup into a *different* clinic works the same way (useful for moving a clinic to
another server). Staff there are matched by e-mail as above.

## Limits and configuration

| Setting | Default | Notes |
|---|---|---|
| `AERODENT_IMPORT_MAX_MB` | `2048` | Largest backup file accepted by the import route. Only this route accepts large bodies; uploads are spooled to a temporary file. The ZIP's uncompressed size may be at most 4× this (zip-bomb protection). |
| Export rate | 10 per hour per user | Exports read every record and image. |
| Import rate | 5 per hour per user | |

A reverse proxy in front of the app must also allow request bodies of that size on
`/api/clinic/import` (for nginx: `client_max_body_size`).

## API

* `GET /api/clinic/export` → `application/zip` attachment.
* `POST /api/clinic/import` (multipart: `file`, `password`) → `{"data": {"counts": {...},
  "skipped": {...}, "unmatched_staff": [...], "source_clinic": ..., "exported_at": ...}}`.
  Errors: 400 invalid or damaged archive, 403 wrong password or not a head doctor,
  413 too large, 429 rate limited.
