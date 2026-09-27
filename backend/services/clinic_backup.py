"""
Complete clinic backup: export every piece of a clinic's data to one ZIP archive, and restore
(import) a clinic from such an archive. Format and rules: docs/CLINIC_BACKUP.md.

Archive layout
    manifest.json                 format, version, counts, SHA-256 of every file
    data.json                     clinic settings, staff list, audit log and every data table
    xrays/<image id>/data         stored X-ray image bytes (exactly as in the database)
    xrays/<image id>/preview      display preview (TIFF etc.), when one exists
    legacy_xrays/<x-ray id>       X-rays still in the old file storage, as uploaded

Import replaces the clinic's data in a single transaction: if anything in the archive is
invalid, nothing changes. IDs are never trusted: every row gets a new ID and every reference is
remapped through the rows of the same archive, so an archive can never point into another
clinic. Staff accounts and the audit log are never overwritten (see _import_*).
"""

import hashlib
import json
import re
import tempfile
import zipfile
from datetime import date, datetime, time, timezone
from decimal import Decimal, InvalidOperation

from flask import current_app
from sqlalchemy import LargeBinary, func, insert, select, text

from backend.extensions import db

FORMAT = "aerodent-clinic-backup"
VERSION = 1

# Restored on import, parents before children. Every clinic-scoped table except `users` and
# `audit_logs` must be listed here; backend/test_clinic_backup.py enforces that.
DATA_TABLES = (
    "patients",
    "treatments",
    "treatment_plans",
    "appointments",
    "waitlist",
    "odontograms",
    "prescriptions",
    "prescription_medications",
    "x_rays",
    "xray_images",
    "invoices",
    "payments",
    "inventory_categories",
    "inventory_suppliers",
    "inventory_items",
    "inventory_batches",
    "inventory_movements",
    "staff_shifts",
    "time_clocks",
    "staff_credentials",
)

CLINIC_SETTINGS_FIELDS = (
    "name",
    "phone",
    "address",
    "currency",
    "work_start",
    "work_end",
    "slot_duration",
    "inventory_expiry_warning_days",
)

# Rows that describe a specific staff member are skipped when that person has no account in
# the importing clinic (e.g. a shift for someone who left). Authorship columns fall back to the
# head doctor performing the import; other staff links (e.g. the assigned doctor) are cleared
# where the column allows it.
STAFF_SUBJECT_COLUMNS = {
    ("staff_shifts", "user_id"),
    ("time_clocks", "user_id"),
    ("staff_credentials", "user_id"),
}

AUTHOR_COLUMNS = {"created_by", "uploaded_by"}

MOVEMENT_REFERENCE_TABLES = {"patient": "patients", "treatment": "treatments", "appointment": "appointments"}

_IMAGE_ENTRY = re.compile(r"^xrays/(\d{1,10})/(data|preview)$")
_LEGACY_ENTRY = re.compile(r"^legacy_xrays/(\d{1,10})$")
MAX_ENTRIES = 500_000
INSERT_CHUNK = 1000


class BackupError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.message = message
        self.status = status


def _table(name):
    return db.metadata.tables[name]


def _sha256(data):
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# Value encoding
# ---------------------------------------------------------------------------

def _encode(value):
    if value is None or isinstance(value, (bool, int, str, float)):
        return value
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, (dict, list)):
        return value
    raise TypeError(f"Cannot export value of type {type(value).__name__}")


def _python_type(column):
    try:
        return column.type.python_type
    except NotImplementedError:
        return None


def _decode(table_name, column, value):
    """Converts a JSON value back to the column's Python type, rejecting anything malformed."""
    if value is None:
        return None
    kind = _python_type(column)
    where = f"{table_name}.{column.name}"
    try:
        if kind is bool:
            if not isinstance(value, bool):
                raise ValueError
            return value
        if kind is int:
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError
            return value
        if kind is Decimal:
            if isinstance(value, bool) or not isinstance(value, (str, int, float)):
                raise ValueError
            return Decimal(str(value))
        if kind is str:
            if not isinstance(value, str):
                raise ValueError
            length = getattr(column.type, "length", None)
            if length and len(value) > length:
                raise BackupError(f"{where} is longer than {length} characters.")
            return value
        if kind is datetime:
            return datetime.fromisoformat(value)
        if kind is date:
            return date.fromisoformat(value)
        if kind is time:
            return time.fromisoformat(value)
        if kind in (dict, list):
            return value
    except BackupError:
        raise
    except (ValueError, TypeError, InvalidOperation):
        raise BackupError(f"Invalid value for {where}.") from None
    raise BackupError(f"Unsupported column {where}.")


def _data_columns(table):
    return [c for c in table.columns if not isinstance(c.type, LargeBinary)]


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

def _rows(table_name, clinic_id):
    table = _table(table_name)
    columns = _data_columns(table)
    if table_name == "prescription_medications":
        prescriptions = _table("prescriptions")
        query = (
            select(*columns)
            .join(prescriptions, prescriptions.c.id == table.c.prescription_id)
            .where(prescriptions.c.clinic_id == clinic_id)
        )
    else:
        query = select(*columns).where(table.c.clinic_id == clinic_id)
    result = db.session.execute(query.order_by(table.c.id))
    return [
        {column.name: _encode(value) for column, value in zip(columns, row) if column.name != "clinic_id"}
        for row in result
    ]


def _schema_revision():
    try:
        return db.session.execute(text("SELECT version_num FROM alembic_version")).scalar()
    except Exception:  # noqa: BLE001 - informational only
        db.session.rollback()
        return None


def export_archive(clinic, exported_by):
    """Builds the backup ZIP and returns (file object positioned at 0, summary counts)."""
    clinic_id = clinic.id
    tables = {name: _rows(name, clinic_id) for name in DATA_TABLES}

    users = _table("users")
    staff = [
        {
            "id": row.id,
            "name": row.name,
            "email": row.email,
            "role": row.role,
            "is_active": row.is_active,
            "created_at": _encode(row.created_at),
        }
        for row in db.session.execute(
            select(users.c.id, users.c.name, users.c.email, users.c.role, users.c.is_active, users.c.created_at)
            .where(users.c.clinic_id == clinic_id)
            .order_by(users.c.id)
        )
    ]
    audit_logs = _rows_plain("audit_logs", clinic_id)

    data = {
        "clinic": {field: _encode(getattr(clinic, field)) for field in CLINIC_SETTINGS_FIELDS},
        "staff": staff,
        "audit_logs": audit_logs,
        "tables": tables,
    }

    files = {}
    corrupt_images = []
    archive = tempfile.SpooledTemporaryFile(max_size=64 * 1024 * 1024)
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        zf.writestr("data.json", payload)
        files["data.json"] = _sha256(payload)

        images = _table("xray_images")
        for image_id in [row["id"] for row in tables["xray_images"]]:
            stored, preview = db.session.execute(
                select(images.c.data, images.c.preview_data).where(images.c.id == image_id)
            ).one()
            # Images are stored, not re-compressed: the bytes in the archive are exactly the
            # database bytes (already lossless PNG or the untouched original).
            zf.writestr(f"xrays/{image_id}/data", bytes(stored), compress_type=zipfile.ZIP_STORED)
            files[f"xrays/{image_id}/data"] = _sha256(bytes(stored))
            recorded = next(row["sha256"] for row in tables["xray_images"] if row["id"] == image_id)
            if files[f"xrays/{image_id}/data"] != recorded:
                # Already damaged in the database: exported as-is (so the backup stays faithful
                # and importable) and named here so nobody mistakes it for a good image.
                corrupt_images.append(image_id)
            if preview is not None:
                zf.writestr(f"xrays/{image_id}/preview", bytes(preview), compress_type=zipfile.ZIP_STORED)
                files[f"xrays/{image_id}/preview"] = _sha256(bytes(preview))

        with_image = {row["xray_id"] for row in tables["xray_images"]}
        for xray in tables["x_rays"]:
            if xray["id"] in with_image or not xray.get("storage_key"):
                continue
            legacy = _read_legacy_file(xray["storage_key"])
            if legacy is not None:
                zf.writestr(f"legacy_xrays/{xray['id']}", legacy, compress_type=zipfile.ZIP_STORED)
                files[f"legacy_xrays/{xray['id']}"] = _sha256(legacy)

        counts = {name: len(rows) for name, rows in tables.items()}
        counts["staff"] = len(staff)
        counts["audit_logs"] = len(audit_logs)
        manifest = {
            "format": FORMAT,
            "version": VERSION,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "schema_revision": _schema_revision(),
            "clinic": {"id": clinic_id, "name": clinic.name},
            "exported_by": {"id": exported_by.id, "name": exported_by.name, "email": exported_by.email},
            "counts": counts,
            "files": files,
            "corrupt_images": corrupt_images,
        }
        zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))

    archive.seek(0)
    return archive, counts


def _rows_plain(table_name, clinic_id):
    table = _table(table_name)
    result = db.session.execute(select(table).where(table.c.clinic_id == clinic_id).order_by(table.c.id))
    return [
        {column.name: _encode(value) for column, value in zip(table.columns, row) if column.name != "clinic_id"}
        for row in result
    ]


def _read_legacy_file(storage_key):
    from backend.services.storage import LocalFileStorage

    try:
        with LocalFileStorage(current_app.config["AERODENT_STORAGE_PATH"]).open(storage_key) as handle:
            return handle.read()
    except Exception:  # noqa: BLE001 - a missing legacy file is reported by `flask xrays verify`
        current_app.logger.warning("Legacy X-ray file %s could not be read for export", storage_key)
        return None


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------

def _open_archive(fileobj, max_uncompressed):
    try:
        zf = zipfile.ZipFile(fileobj)
    except (zipfile.BadZipFile, OSError, ValueError):
        raise BackupError("This file is not an AeroDent clinic backup (expected a .zip file).") from None

    infos = zf.infolist()
    if len(infos) > MAX_ENTRIES:
        raise BackupError("The backup contains too many files.")
    total = 0
    for info in infos:
        name = info.filename
        if name not in ("manifest.json", "data.json") and not (_IMAGE_ENTRY.match(name) or _LEGACY_ENTRY.match(name)):
            raise BackupError("The backup contains unexpected files.")
        total += info.file_size
    # Archives are read entry by entry into memory, never extracted to disk, so entry names
    # cannot escape anywhere; the size check stops compression bombs.
    if total > max_uncompressed:
        raise BackupError("The backup is too large to import.", 413)
    return zf


def _read_entry(zf, name, expected_sha256):
    try:
        payload = zf.read(name)
    except KeyError:
        raise BackupError(f"The backup is missing {name}.") from None
    except (zipfile.BadZipFile, OSError, RuntimeError):
        raise BackupError(f"{name} in the backup is damaged.") from None
    if expected_sha256 is not None and _sha256(payload) != expected_sha256:
        raise BackupError(f"{name} in the backup is damaged (checksum mismatch).")
    return payload


def read_archive(fileobj, max_uncompressed):
    zf = _open_archive(fileobj, max_uncompressed)
    try:
        manifest = json.loads(_read_entry(zf, "manifest.json", None))
    except (ValueError, UnicodeDecodeError):
        raise BackupError("The backup manifest is not valid JSON.") from None
    if not isinstance(manifest, dict) or manifest.get("format") != FORMAT:
        raise BackupError("This file is not an AeroDent clinic backup.")
    if manifest.get("version") != VERSION:
        raise BackupError("This backup was made by a different AeroDent version and cannot be imported here.")
    files = manifest.get("files")
    if not isinstance(files, dict) or "data.json" not in files:
        raise BackupError("The backup manifest is incomplete.")
    try:
        data = json.loads(_read_entry(zf, "data.json", files["data.json"]))
    except (ValueError, UnicodeDecodeError):
        raise BackupError("The backup data is not valid JSON.") from None
    if not isinstance(data, dict) or not isinstance(data.get("tables"), dict):
        raise BackupError("The backup data is incomplete.")
    return zf, manifest, data


def _validated_rows(data, table_name):
    table = _table(table_name)
    rows = data["tables"].get(table_name, [])
    if not isinstance(rows, list):
        raise BackupError(f"Invalid data for {table_name}.")
    known = {c.name for c in table.columns}
    seen = set()
    for row in rows:
        if not isinstance(row, dict) or isinstance(row.get("id"), bool) or not isinstance(row.get("id"), int):
            raise BackupError(f"Invalid row in {table_name}.")
        unknown = set(row) - known
        if unknown:
            raise BackupError(
                f"{table_name} has columns this server does not know ({', '.join(sorted(unknown))}); "
                "the backup was probably made by a newer version."
            )
        if row["id"] in seen:
            raise BackupError(f"Duplicate row id in {table_name}.")
        seen.add(row["id"])
    return rows


def _references(table):
    """{column name: referred table} for every foreign key except the clinic itself."""
    refs = {}
    for constraint in table.foreign_key_constraints:
        if constraint.referred_table.name == "clinics":
            continue
        for column in constraint.columns:
            if column.name != "clinic_id":
                refs[column.name] = constraint.referred_table.name
    return refs


def delete_clinic_data(clinic_id):
    """Removes the clinic's current data (children first). Staff and audit log are kept."""
    legacy_keys = list(
        db.session.scalars(
            select(_table("x_rays").c.storage_key).where(
                _table("x_rays").c.clinic_id == clinic_id, _table("x_rays").c.storage_key.is_not(None)
            )
        )
    )
    for table_name in reversed(DATA_TABLES):
        table = _table(table_name)
        if table_name == "prescription_medications":
            prescriptions = _table("prescriptions")
            db.session.execute(
                table.delete().where(
                    table.c.prescription_id.in_(select(prescriptions.c.id).where(prescriptions.c.clinic_id == clinic_id))
                )
            )
        else:
            db.session.execute(table.delete().where(table.c.clinic_id == clinic_id))
    return legacy_keys


def import_archive(clinic, importer, zf, manifest, data):
    """
    Replaces the clinic's data with the archive's. Runs inside the caller's transaction; the
    caller commits on success and rolls back on BackupError.
    """
    from backend.services.xray_images import XRayImageError, process_upload

    files = manifest["files"]
    rows_by_table = {name: _validated_rows(data, name) for name in DATA_TABLES}

    # Staff are matched by e-mail to accounts that already exist in this clinic.
    users = _table("users")
    current_staff = {
        email.lower(): user_id
        for user_id, email in db.session.execute(
            select(users.c.id, users.c.email).where(users.c.clinic_id == clinic.id)
        )
    }
    staff = data.get("staff") if isinstance(data.get("staff"), list) else []
    user_map, unmatched = {}, []
    for person in staff:
        if not isinstance(person, dict) or not isinstance(person.get("id"), int) or not isinstance(person.get("email"), str):
            raise BackupError("Invalid staff entry in the backup.")
        match = current_staff.get(person["email"].strip().lower())
        user_map[person["id"]] = match
        if match is None:
            unmatched.append(person["email"])

    legacy_keys = delete_clinic_data(clinic.id)

    id_maps = {name: {} for name in DATA_TABLES}
    counts, skipped = {}, {}
    for table_name in DATA_TABLES:
        table = _table(table_name)
        refs = _references(table)
        columns = {c.name: c for c in _data_columns(table)}
        prepared, old_ids = [], []
        for row in rows_by_table[table_name]:
            values = {}
            skip = False
            for name, column in columns.items():
                if name == "id":
                    continue
                if name == "clinic_id":
                    values[name] = clinic.id
                    continue
                raw = row.get(name)
                if name in refs and raw is not None:
                    target = refs[name]
                    if isinstance(raw, bool) or not isinstance(raw, int):
                        raise BackupError(f"Invalid reference {table_name}.{name}.")
                    if target == "users":
                        mapped = user_map.get(raw)
                        if mapped is None:
                            if (table_name, name) in STAFF_SUBJECT_COLUMNS:
                                skip = True
                                break
                            mapped = importer.id if name in AUTHOR_COLUMNS or not column.nullable else None
                        values[name] = mapped
                    else:
                        if raw not in id_maps[target]:
                            raise BackupError(f"{table_name} refers to a {target} row that is not in the backup.")
                        values[name] = id_maps[target][raw]
                    continue
                values[name] = _decode(table_name, column, raw)
            if skip:
                skipped[table_name] = skipped.get(table_name, 0) + 1
                continue

            if table_name == "x_rays":
                values["storage_key"] = None  # old file-storage paths mean nothing on this server
            if table_name == "inventory_movements" and values.get("reference_type") is not None:
                target = MOVEMENT_REFERENCE_TABLES.get(values["reference_type"])
                old = values.get("reference_id")
                if target is None or old not in id_maps[target]:
                    raise BackupError("An inventory movement refers to a record that is not in the backup.")
                values["reference_id"] = id_maps[target][old]
            if table_name == "xray_images":
                name = f"xrays/{row['id']}/data"
                if name not in files:
                    raise BackupError(f"The backup is missing {name}.")
                # _read_entry checks the bytes against the manifest (damage in the file itself).
                stored = _read_entry(zf, name, files[name])
                known_corrupt = row["id"] in (manifest.get("corrupt_images") or [])
                if not known_corrupt and (_sha256(stored) != values.get("sha256") or len(stored) != values.get("size_bytes")):
                    raise BackupError("An X-ray image in the backup does not match its checksum.")
                values["data"] = stored
                preview_name = f"xrays/{row['id']}/preview"
                values["preview_data"] = (
                    _read_entry(zf, preview_name, files.get(preview_name)) if preview_name in files else None
                )
            prepared.append(values)
            old_ids.append(row["id"])

        new_ids = []
        for start in range(0, len(prepared), INSERT_CHUNK):
            chunk = prepared[start:start + INSERT_CHUNK]
            result = db.session.execute(
                insert(table).returning(table.c.id, sort_by_parameter_order=True), chunk
            )
            new_ids.extend(result.scalars().all())
        id_maps[table_name] = dict(zip(old_ids, new_ids))
        counts[table_name] = len(new_ids)

    # X-rays that were still in the old file storage when exported become database images now.
    images = _table("xray_images")
    xrays = _table("x_rays")
    with_image = {row["xray_id"] for row in rows_by_table["xray_images"]}
    for old_xray_id, new_xray_id in id_maps["x_rays"].items():
        name = f"legacy_xrays/{old_xray_id}"
        if old_xray_id in with_image or name not in files:
            continue
        content = _read_entry(zf, name, files[name])
        filename = db.session.execute(select(xrays.c.filename).where(xrays.c.id == new_xray_id)).scalar()
        try:
            fields = process_upload(content, original_filename=filename)
        except XRayImageError as error:
            raise BackupError(f"An X-ray in the backup could not be read: {error}") from None
        db.session.execute(insert(images).values(clinic_id=clinic.id, xray_id=new_xray_id, **fields))
        counts["xray_images"] = counts.get("xray_images", 0) + 1

    settings = data.get("clinic") if isinstance(data.get("clinic"), dict) else {}
    clinics = _table("clinics")
    updates = {
        field: _decode("clinic", clinics.c[field], settings[field])
        for field in CLINIC_SETTINGS_FIELDS
        if field in settings
    }
    if updates.get("name") in (None, ""):
        updates.pop("name", None)
    if updates:
        db.session.execute(clinics.update().where(clinics.c.id == clinic.id).values(**updates))

    return {
        "counts": counts,
        "skipped": skipped,
        "unmatched_staff": sorted(set(unmatched)),
        "source_clinic": manifest.get("clinic", {}).get("name"),
        "exported_at": manifest.get("exported_at"),
        "legacy_keys": legacy_keys,
    }


def count_clinic_rows(clinic_id):
    """Row counts per data table (used by tests and the import summary)."""
    counts = {}
    for name in DATA_TABLES:
        table = _table(name)
        if name == "prescription_medications":
            prescriptions = _table("prescriptions")
            query = select(func.count()).select_from(table).join(
                prescriptions, prescriptions.c.id == table.c.prescription_id
            ).where(prescriptions.c.clinic_id == clinic_id)
        else:
            query = select(func.count()).select_from(table).where(table.c.clinic_id == clinic_id)
        counts[name] = db.session.execute(query).scalar()
    return counts



def load_backup_bytes(raw):
    """(manifest, data) of an exported archive held in memory. Used by tests and tooling."""
    import io

    zf, manifest, data = read_archive(io.BytesIO(raw), max_uncompressed=1 << 34)
    zf.close()
    return manifest, data
