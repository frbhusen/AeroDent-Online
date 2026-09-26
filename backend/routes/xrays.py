from datetime import date, datetime
from io import BytesIO

from flask import Blueprint, current_app, g, jsonify, request, send_file
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload, undefer
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

from backend.auth import login_required, require_permission
from backend.extensions import db
from backend.models import Patient, XRay, XRayImage
from backend.services.audit import log_activity
from backend.services.auth_security import rate_limited
from backend.services.storage import LocalFileStorage
from backend.services.xray_images import (
    XRayImageError,
    download_name,
    process_upload,
    verify_bytes,
    verify_full,
)


xrays_blueprint = Blueprint("xrays", __name__, url_prefix="/api")

XRAY_METADATA_FIELDS = frozenset({"filename", "tooth_tag", "type", "date", "time", "notes"})
XRAY_INTERNAL_FIELDS = frozenset(
    {"id", "clinic_id", "patient_id", "uploaded_by", "storage_key", "created_at", "updated_at"}
)
UPLOADS_PER_HOUR = 200
MAX_METADATA_LENGTHS = {"filename": 255, "tooth_tag": 100, "type": 100, "notes": 2000}


def _error(message, status):
    return jsonify({"error": message}), status


def _validate_metadata_lengths(data):
    for field, max_len in MAX_METADATA_LENGTHS.items():
        value = data.get(field)
        if isinstance(value, str) and len(value) > max_len:
            return _error(f"{field} must be at most {max_len} characters.", 422)
    return None


def _legacy_storage():
    """Filesystem storage used only for X-rays uploaded before images moved into PostgreSQL."""
    return LocalFileStorage(current_app.config["AERODENT_STORAGE_PATH"])


def _scoped_patient(patient_id):
    return db.session.scalar(
        db.select(Patient).where(
            Patient.id == patient_id,
            Patient.clinic_id == g.current_user.clinic_id,
        )
    )


def _scoped_xray(xray_id):
    return db.session.scalar(
        db.select(XRay).where(
            XRay.id == xray_id,
            XRay.clinic_id == g.current_user.clinic_id,
        )
    )


def _parse_date(value):
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _parse_time(value):
    if value in (None, ""):
        return None
    try:
        return datetime.strptime(value, "%H:%M").time()
    except (TypeError, ValueError):
        return None


def _serialize_xray(xray):
    return {
        "id": xray.id,
        "patient_id": xray.patient_id,
        "filename": xray.filename,
        "mime_type": xray.mime_type,
        "original_mime_type": xray.original_mime_type,
        "tooth_tag": xray.tooth_tag,
        "type": xray.type,
        "date": xray.date.isoformat(),
        "time": xray.time.isoformat() if xray.time else None,
        "notes": xray.notes,
        "uploaded_by": xray.uploaded_by,
        "image": _serialize_image(xray.image),
        "created_at": xray.created_at.isoformat() if xray.created_at else None,
        "updated_at": xray.updated_at.isoformat() if xray.updated_at else None,
    }


def _serialize_image(image):
    if image is None:
        return None
    return {
        "format": image.image_format,
        "mime_type": image.mime_type,
        "encoding": image.encoding,
        "lossless": image.encoding in ("original", "png-lossless"),
        "size_bytes": image.size_bytes,
        "original_size_bytes": image.original_size_bytes,
        "width": image.width,
        "height": image.height,
        "color_mode": image.color_mode,
        "sha256": image.sha256,
        "original_sha256": image.original_sha256,
        "has_preview": image.preview_mime_type is not None,
    }


def _read_upload(file_storage):
    if not isinstance(file_storage, FileStorage) or not file_storage.filename:
        return None, _error("An image file is required.", 400)
    max_bytes = current_app.config["XRAY_MAX_UPLOAD_BYTES"]
    content = file_storage.stream.read(max_bytes + 1)
    if len(content) > max_bytes:
        return None, _error("Image file is too large.", 413)
    return content, None


def _metadata_from_form(form):
    data = {}
    filename = form.get("filename")
    if filename is not None:
        safe_name = secure_filename(filename)
        if not safe_name:
            return None, _error("filename is invalid.", 422)
        data["filename"] = safe_name

    for field in ("tooth_tag", "type", "notes"):
        value = form.get(field)
        if value is not None:
            if not isinstance(value, str):
                return None, _error(f"{field} must be text.", 422)
            data[field] = value

    if "date" in form:
        parsed_date = _parse_date(form.get("date"))
        if parsed_date is None:
            return None, _error("date must be an ISO date.", 422)
        data["date"] = parsed_date

    if "time" in form:
        raw_time = form.get("time")
        if raw_time not in ("", None) and _parse_time(raw_time) is None:
            return None, _error("time must use HH:MM format.", 422)
        data["time"] = _parse_time(raw_time)

    length_error = _validate_metadata_lengths(data)
    if length_error:
        return None, length_error

    return data, None


@xrays_blueprint.post("/patients/<int:patient_id>/x-rays")
@login_required
@require_permission("xrays.create")
def upload_xray(patient_id):
    patient = _scoped_patient(patient_id)
    if patient is None:
        return _error("Patient not found.", 404)

    retry_after = rate_limited("xray_upload_user", g.current_user.id, limit=UPLOADS_PER_HOUR, window_seconds=3600)
    db.session.commit()
    if retry_after:
        return _error("Upload limit reached. Please try again later.", 429)

    file_item = request.files.get("file")
    content, error = _read_upload(file_item)
    if error:
        return error
    metadata, error = _metadata_from_form(request.form)
    if error:
        return error

    original_name = secure_filename(file_item.filename) or "xray"
    try:
        image_fields = process_upload(content, original_name[:255], file_item.mimetype)
    except XRayImageError as exc:
        return _error(exc.message, exc.status)

    metadata.setdefault("filename", original_name[:255])
    metadata.setdefault("date", date.today())

    # Record and image bytes are written in ONE transaction: either both exist or neither.
    xray = XRay(
        **metadata,
        clinic_id=g.current_user.clinic_id,
        patient_id=patient.id,
        uploaded_by=g.current_user.id,
        storage_key=None,
        mime_type=image_fields["mime_type"],
        original_mime_type=image_fields["original_mime_type"],
    )
    xray.image = XRayImage(clinic_id=g.current_user.clinic_id, **image_fields)
    db.session.add(xray)
    try:
        db.session.flush()
        log_activity(
            action="xray_uploaded",
            resource_type="xray",
            resource_id=xray.id,
            clinic_id=xray.clinic_id,
            details={
                "patient_id": xray.patient_id,
                "type": xray.type,
                "format": xray.image.image_format,
                "encoding": xray.image.encoding,
                "size_bytes": xray.image.size_bytes,
                "sha256": xray.image.sha256,
            },
        )
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return _error("X-ray could not be saved.", 409)

    return jsonify({"data": _serialize_xray(xray)}), 201


@xrays_blueprint.get("/patients/<int:patient_id>/x-rays")
@login_required
@require_permission("xrays.read")
def list_xrays(patient_id):
    patient = _scoped_patient(patient_id)
    if patient is None:
        return _error("Patient not found.", 404)

    query = db.select(XRay).where(
        XRay.patient_id == patient.id,
        XRay.clinic_id == g.current_user.clinic_id,
    )
    for field in ("tooth_tag", "type"):
        if field in request.args:
            query = query.where(getattr(XRay, field) == request.args[field])
    if "date" in request.args:
        requested_date = _parse_date(request.args["date"])
        if requested_date is None:
            return _error("date must be an ISO date.", 422)
        query = query.where(XRay.date == requested_date)

    records = db.session.scalars(
        query.options(selectinload(XRay.image)).order_by(XRay.date.desc(), XRay.id.desc())
    ).all()
    return jsonify({"data": [_serialize_xray(item) for item in records], "meta": {"count": len(records)}})


@xrays_blueprint.get("/x-rays/<int:xray_id>")
@login_required
@require_permission("xrays.read")
def get_xray(xray_id):
    xray = _scoped_xray(xray_id)
    if xray is None:
        return _error("X-ray not found.", 404)
    return jsonify({"data": _serialize_xray(xray)})


def _load_image_bytes(xray, *, preview=False):
    column = XRayImage.preview_data if preview else XRayImage.data
    return db.session.scalar(
        db.select(column).where(XRayImage.clinic_id == xray.clinic_id, XRayImage.xray_id == xray.id)
    )


def _private_file_response(data, mimetype, filename, as_attachment):
    response = send_file(BytesIO(data), mimetype=mimetype, as_attachment=as_attachment, download_name=filename)
    response.headers["Cache-Control"] = "no-store, private"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Content-Security-Policy"] = "default-src 'none'; sandbox"
    return response


@xrays_blueprint.get("/x-rays/<int:xray_id>/file")
@login_required
@require_permission("xrays.read")
def get_xray_file(xray_id):
    """
    ?download=1  -> the stored (original or lossless) bytes as an attachment
    default      -> inline display; formats browsers cannot render use the preview rendition
    """
    xray = _scoped_xray(xray_id)
    if xray is None:
        return _error("X-ray not found.", 404)
    as_attachment = request.args.get("download") == "1"
    record = xray.image

    if record is None:
        return _legacy_file_response(xray, as_attachment)

    if not as_attachment and record.preview_mime_type:
        preview = _load_image_bytes(xray, preview=True)
        if preview:
            return _private_file_response(preview, record.preview_mime_type, download_name(xray.filename, "PNG"), False)

    data = _load_image_bytes(xray)
    if not verify_bytes(record, data):
        current_app.logger.error("Integrity check failed for X-ray %s (clinic %s)", xray.id, xray.clinic_id)
        log_activity(
            action="xray_integrity_failed",
            resource_type="xray",
            resource_id=xray.id,
            clinic_id=xray.clinic_id,
            details={"expected_sha256": record.sha256},
        )
        db.session.commit()
        return _error("This X-ray failed its integrity check and cannot be served.", 409)

    if as_attachment:
        log_activity(action="xray_downloaded", resource_type="xray", resource_id=xray.id, clinic_id=xray.clinic_id)
        db.session.commit()
    return _private_file_response(data, record.mime_type, download_name(xray.filename, record.image_format), as_attachment)


def _legacy_file_response(xray, as_attachment):
    if not xray.storage_key:
        return _error("X-ray file not found.", 404)
    try:
        with _legacy_storage().open(xray.storage_key) as handle:
            data = handle.read()
    except (FileNotFoundError, ValueError, OSError):
        return _error("X-ray file not found.", 404)
    return _private_file_response(data, xray.mime_type or "image/webp", xray.filename, as_attachment)


@xrays_blueprint.get("/x-rays/<int:xray_id>/verify")
@login_required
@require_permission("xrays.read")
def verify_xray(xray_id):
    xray = _scoped_xray(xray_id)
    if xray is None:
        return _error("X-ray not found.", 404)
    record = db.session.scalar(
        db.select(XRayImage)
        .options(undefer(XRayImage.data))
        .where(XRayImage.clinic_id == xray.clinic_id, XRayImage.xray_id == xray.id)
    )
    if record is None:
        return jsonify({"data": {"id": xray.id, "verified": False, "reason": "no database-stored image (legacy file)"}})
    ok, reason = verify_full(record, record.data)
    return jsonify({"data": {"id": xray.id, "verified": ok, "reason": reason, "sha256": record.sha256}})


@xrays_blueprint.patch("/x-rays/<int:xray_id>")
@login_required
@require_permission("xrays.update")
def update_xray(xray_id):
    xray = _scoped_xray(xray_id)
    if xray is None:
        return _error("X-ray not found.", 404)
    if request.files:
        return _error("X-ray file replacement is not supported.", 400)

    data, error = _metadata_from_form(request.form) if request.form else (request.get_json(silent=True), None)
    if error:
        return error
    if not isinstance(data, dict):
        return _error("Request body must contain metadata.", 400)
    unsupported = set(data) - XRAY_METADATA_FIELDS
    if unsupported & XRAY_INTERNAL_FIELDS:
        return _error("X-ray ownership fields are server-controlled.", 400)
    if unsupported:
        return _error("Unsupported X-ray field.", 400)
    if not data:
        return _error("At least one X-ray field is required.", 400)

    if request.is_json:
        if "date" in data:
            parsed_date = _parse_date(data["date"])
            if parsed_date is None:
                return _error("date must be an ISO date.", 422)
            data["date"] = parsed_date
        if "time" in data:
            parsed_time = _parse_time(data["time"])
            if data["time"] not in (None, "") and parsed_time is None:
                return _error("time must use HH:MM format.", 422)
            data["time"] = parsed_time
        for field in ("filename", "tooth_tag", "type", "notes"):
            if field in data and data[field] is not None and not isinstance(data[field], str):
                return _error(f"{field} must be text.", 422)
        if "filename" in data:
            data["filename"] = secure_filename(data["filename"])
            if not data["filename"]:
                return _error("filename is invalid.", 422)

        length_error = _validate_metadata_lengths(data)
        if length_error:
            return length_error

    for field, value in data.items():
        setattr(xray, field, value)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return _error("X-ray could not be updated.", 409)
    return jsonify({"data": _serialize_xray(xray)})


@xrays_blueprint.delete("/x-rays/<int:xray_id>")
@login_required
@require_permission("xrays.delete")
def delete_xray(xray_id):
    xray = _scoped_xray(xray_id)
    if xray is None:
        return _error("X-ray not found.", 404)
    legacy_key = xray.storage_key
    log_activity(
        action="xray_deleted",
        resource_type="xray",
        resource_id=xray.id,
        clinic_id=xray.clinic_id,
        details={
            "patient_id": xray.patient_id,
            "filename": xray.filename,
        },
    )
    db.session.delete(xray)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return _error("X-ray could not be deleted.", 409)
    if legacy_key:
        try:
            _legacy_storage().delete(legacy_key)
        except (OSError, ValueError):
            current_app.logger.exception("Failed to clean up legacy X-ray file %s", legacy_key)
    return "", 204