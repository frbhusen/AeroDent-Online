from datetime import datetime, time
from flask import Blueprint, current_app, g, jsonify, request, send_file
from sqlalchemy.exc import DataError, IntegrityError

from backend.auth import login_required, require_permission
from backend.extensions import db
from backend.services.audit import log_activity
from backend.auth.service import verify_password
from backend.services.auth_security import clear_failures, failure_lock_wait, rate_limited, record_failure
from backend.services.clinic_backup import BackupError, export_archive, import_archive, read_archive
from backend.services.storage import LocalFileStorage


settings_blueprint = Blueprint("settings", __name__, url_prefix="/api")

ALLOWED_SETTING_FIELDS = frozenset(
    {
        "name",
        "phone",
        "address",
        "currency",
        "work_start",
        "work_end",
        "slot_duration",
        "inventory_expiry_warning_days",
    }
)


def _error(message, status):
    return jsonify({"error": message}), status


def _parse_time(value):
    if not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value, "%H:%M").time()
    except ValueError:
        return None


def _serialize_settings(clinic):
    return {
        "id": clinic.id,
        "name": clinic.name,
        "phone": clinic.phone or "",
        "address": clinic.address or "",
        "currency": clinic.currency or "SYR",
        "work_start": clinic.work_start.strftime("%H:%M") if clinic.work_start else "09:00",
        "work_end": clinic.work_end.strftime("%H:%M") if clinic.work_end else "18:00",
        "slot_duration": clinic.slot_duration or 30,
        "inventory_expiry_warning_days": clinic.inventory_expiry_warning_days or 60,
        "created_at": clinic.created_at.isoformat() if clinic.created_at else None,
        "updated_at": clinic.updated_at.isoformat() if clinic.updated_at else None,
    }


@settings_blueprint.get("/settings")
@login_required
@require_permission("clinic_settings.read")
def get_settings():
    clinic = g.current_clinic
    return jsonify({"data": _serialize_settings(clinic)})


@settings_blueprint.patch("/settings")
@login_required
@require_permission("clinic_settings.update")
def update_settings():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return _error("Request body must be a JSON object.", 400)

    unsupported = set(data) - ALLOWED_SETTING_FIELDS
    if unsupported:
        return _error("Unsupported settings field.", 400)

    if not data:
        return _error("At least one settings field is required.", 400)

    clinic = g.current_clinic

    if "name" in data:
        if not isinstance(data["name"], str) or not data["name"].strip():
            return _error("Clinic name must not be blank.", 422)
        if len(data["name"].strip()) > 150:
            return _error("Clinic name is too long.", 422)
        clinic.name = data["name"].strip()

    if "phone" in data:
        if data["phone"] is not None and not isinstance(data["phone"], str):
            return _error("Phone must be a string or null.", 422)
        clinic.phone = data["phone"].strip() if data["phone"] else None

    if "address" in data:
        if data["address"] is not None and not isinstance(data["address"], str):
            return _error("Address must be a string or null.", 422)
        clinic.address = data["address"].strip() if data["address"] else None

    if "currency" in data:
        if not isinstance(data["currency"], str) or not data["currency"].strip():
            return _error("Currency must not be blank.", 422)
        if len(data["currency"].strip()) > 10:
            return _error("Currency code is too long.", 422)
        clinic.currency = data["currency"].strip()

    work_start = clinic.work_start or time(9, 0)
    work_end = clinic.work_end or time(18, 0)

    if "work_start" in data:
        parsed_start = _parse_time(data["work_start"])
        if parsed_start is None:
            return _error("work_start must be in HH:MM format.", 422)
        work_start = parsed_start

    if "work_end" in data:
        parsed_end = _parse_time(data["work_end"])
        if parsed_end is None:
            return _error("work_end must be in HH:MM format.", 422)
        work_end = parsed_end

    if (work_start.hour * 60 + work_start.minute) >= (work_end.hour * 60 + work_end.minute):
        return _error("work_start must be earlier than work_end.", 422)

    clinic.work_start = work_start
    clinic.work_end = work_end

    if "slot_duration" in data:
        val = data["slot_duration"]
        if isinstance(val, bool) or not isinstance(val, int) or val <= 0 or val > 240:
            return _error("slot_duration must be a positive integer up to 240 minutes.", 422)
        clinic.slot_duration = val

    if "inventory_expiry_warning_days" in data:
        val = data["inventory_expiry_warning_days"]
        if isinstance(val, bool) or not isinstance(val, int) or val < 1 or val > 365:
            return _error("inventory_expiry_warning_days must be an integer between 1 and 365.", 422)
        clinic.inventory_expiry_warning_days = val

    try:
        log_activity(
            action="clinic_settings_updated",
            resource_type="clinic",
            resource_id=clinic.id,
            clinic_id=clinic.id,
            details={
                "name": clinic.name,
                "currency": clinic.currency,
                "slot_duration": clinic.slot_duration,
            },
        )
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return _error("Settings could not be updated.", 409)

    return jsonify({"data": _serialize_settings(clinic)})


def _too_many(retry_after, message):
    response = jsonify({"error": message, "retry_after": retry_after})
    response.status_code = 429
    response.headers["Retry-After"] = str(retry_after)
    return response


@settings_blueprint.get("/clinic/export")
@login_required
@require_permission("clinic_data.export")
def export_clinic_data():
    """Full clinic backup (every record, staff list, audit log and X-ray files) as a ZIP."""
    # Full exports read every clinic record; cap them per user to prevent resource exhaustion.
    retry_after = rate_limited("clinic_export_user", g.current_user.id, limit=10, window_seconds=3600)
    db.session.commit()
    if retry_after:
        return _too_many(retry_after, "Export limit reached. Please try again later.")

    clinic = g.current_clinic
    archive, counts = export_archive(clinic, g.current_user)
    log_activity(
        action="clinic_data_exported",
        resource_type="clinic",
        resource_id=clinic.id,
        details={"counts": counts},
    )
    db.session.commit()
    filename = f"aerodent-clinic-{clinic.id}-{datetime.now().strftime('%Y%m%d-%H%M')}.zip"
    return send_file(archive, mimetype="application/zip", as_attachment=True, download_name=filename, max_age=0)


@settings_blueprint.post("/clinic/import")
@login_required
@require_permission("clinic_data.import")
def import_clinic_data():
    """
    Restores the clinic from a backup ZIP, replacing its current data in one transaction.
    Requires the head doctor's password, because it overwrites every clinical record.
    """
    user = g.current_user
    # Only this route accepts large bodies (set before the form is parsed).
    request.max_content_length = current_app.config["CLINIC_IMPORT_MAX_BYTES"]

    retry_after = failure_lock_wait("clinic_import_password", user.id)
    if retry_after:
        return _too_many(retry_after, "Too many attempts. Please wait before trying again.")
    retry_after = rate_limited("clinic_import_user", user.id, limit=5, window_seconds=3600)
    db.session.commit()
    if retry_after:
        return _too_many(retry_after, "Import limit reached. Please try again later.")

    password = request.form.get("password", "")
    if not isinstance(password, str) or not password or len(password) > 1024 or not verify_password(password, user.password_hash):
        wait = record_failure("clinic_import_password", user.id, policy=(5, 60, 30 * 60))
        log_activity(action="clinic_import_failed", resource_type="clinic", resource_id=user.clinic_id,
                     details={"reason": "wrong_password"})
        db.session.commit()
        if wait:
            return _too_many(wait, "Too many attempts. Please wait before trying again.")
        return _error("Password is incorrect.", 403)
    clear_failures("clinic_import_password", user.id)

    upload = request.files.get("file")
    if upload is None or not upload.filename:
        return _error("Choose a backup file (.zip) to import.", 400)

    clinic = g.current_clinic
    try:
        zf, manifest, data = read_archive(upload.stream, current_app.config["CLINIC_IMPORT_MAX_BYTES"] * 4)
        with zf:
            summary = import_archive(clinic, user, zf, manifest, data)
        log_activity(
            action="clinic_data_imported",
            resource_type="clinic",
            resource_id=clinic.id,
            details={
                "counts": summary["counts"],
                "skipped": summary["skipped"],
                "unmatched_staff": len(summary["unmatched_staff"]),
                "source_clinic": summary["source_clinic"],
                "exported_at": summary["exported_at"],
            },
        )
        db.session.commit()
    except BackupError as error:
        db.session.rollback()
        log_activity(action="clinic_import_failed", resource_type="clinic", resource_id=clinic.id,
                     details={"reason": error.message[:200]})
        db.session.commit()
        return _error(error.message, error.status)
    except (IntegrityError, DataError):
        db.session.rollback()
        current_app.logger.exception("Clinic import rejected by database constraints")
        return _error("The backup contains data that is not valid for this clinic. Nothing was changed.", 400)

    # Old file-storage X-rays of the replaced data are no longer referenced.
    for key in summary.pop("legacy_keys"):
        try:
            LocalFileStorage(current_app.config["AERODENT_STORAGE_PATH"]).delete(key)
        except Exception:  # noqa: BLE001 - best effort cleanup after a successful commit
            current_app.logger.warning("Could not remove replaced legacy X-ray file %s", key)

    return jsonify({"data": summary})
