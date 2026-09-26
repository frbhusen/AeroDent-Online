from datetime import date, datetime
from io import BytesIO
from pathlib import PurePosixPath
from uuid import uuid4

from PIL import Image, UnidentifiedImageError
from flask import Blueprint, current_app, g, jsonify, request, send_file
from sqlalchemy.exc import IntegrityError
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

from backend.auth import login_required, require_permission
from backend.extensions import db
from backend.models import Patient, XRay
from backend.services.storage import LocalFileStorage
from backend.services.audit import log_activity


xrays_blueprint = Blueprint("xrays", __name__, url_prefix="/api")

XRAY_METADATA_FIELDS = frozenset({"filename", "tooth_tag", "type", "date", "time", "notes"})
XRAY_INTERNAL_FIELDS = frozenset(
    {"id", "clinic_id", "patient_id", "uploaded_by", "storage_key", "created_at", "updated_at"}
)
MAX_IMAGE_DIMENSION = 1600
ALLOWED_IMAGE_FORMATS = frozenset({"JPEG", "PNG", "WEBP", "GIF", "BMP", "TIFF"})
MAX_METADATA_LENGTHS = {"filename": 255, "tooth_tag": 100, "type": 100, "notes": 2000}


def _error(message, status):
    return jsonify({"error": message}), status


def _validate_metadata_lengths(data):
    for field, max_len in MAX_METADATA_LENGTHS.items():
        value = data.get(field)
        if isinstance(value, str) and len(value) > max_len:
            return _error(f"{field} must be at most {max_len} characters.", 422)
    return None


def _storage():
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
        "created_at": xray.created_at.isoformat() if xray.created_at else None,
        "updated_at": xray.updated_at.isoformat() if xray.updated_at else None,
    }


def _normalize_image(file_storage):
    if not isinstance(file_storage, FileStorage) or not file_storage.filename:
        return None, _error("An image file is required.", 400)

    max_bytes = current_app.config["XRAY_MAX_UPLOAD_BYTES"]
    content = file_storage.stream.read(max_bytes + 1)
    if len(content) > max_bytes:
        return None, _error("Image file is too large.", 413)

    try:
        with Image.open(BytesIO(content)) as image:
            image.verify()
            image_format = image.format
        if not isinstance(image_format, str) or image_format not in ALLOWED_IMAGE_FORMATS:
            return None, _error("Unsupported image format.", 422)

        with Image.open(BytesIO(content)) as image:
            image.load()
            scale = min(
                1,
                MAX_IMAGE_DIMENSION / image.width,
                MAX_IMAGE_DIMENSION / image.height,
            )
            if scale < 1:
                image = image.resize(
                    (round(image.width * scale), round(image.height * scale)),
                    Image.Resampling.LANCZOS,
                )
            if "A" in image.getbands():
                image = image.convert("RGBA")
            else:
                image = image.convert("RGB")
            output = BytesIO()
            image.save(output, format="WEBP", quality=82, method=6)

        return {
            "content": output.getvalue(),
            "original_mime_type": Image.MIME.get(image_format, "image/" + image_format.lower()),
            "mime_type": "image/webp",
        }, None
    except (UnidentifiedImageError, OSError, ValueError):
        return None, _error("Uploaded file is not a valid image.", 422)


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

    image, error = _normalize_image(request.files.get("file"))
    if error:
        return error
    metadata, error = _metadata_from_form(request.form)
    if error:
        return error

    file_item = request.files.get("file")
    raw_name = file_item.filename if file_item and file_item.filename else "xray.webp"
    metadata.setdefault("filename", secure_filename(raw_name) or "xray.webp")
    metadata.setdefault("date", date.today())
    storage_key = PurePosixPath(
        "clinics",
        str(g.current_user.clinic_id),
        "patients",
        str(patient.id),
        "x-rays",
        f"{uuid4().hex}.webp",
    ).as_posix()
    storage = _storage()
    storage.save(image["content"], storage_key)
    xray = XRay(
        **metadata,
        clinic_id=g.current_user.clinic_id,
        patient_id=patient.id,
        uploaded_by=g.current_user.id,
        storage_key=storage_key,
        mime_type=image["mime_type"],
        original_mime_type=image["original_mime_type"],
    )
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
                "filename": xray.filename,
                "type": xray.type,
            },
        )
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        storage.delete(storage_key)
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

    records = db.session.scalars(query.order_by(XRay.date.desc(), XRay.id.desc())).all()
    return jsonify({"data": [_serialize_xray(item) for item in records], "meta": {"count": len(records)}})


@xrays_blueprint.get("/x-rays/<int:xray_id>")
@login_required
@require_permission("xrays.read")
def get_xray(xray_id):
    xray = _scoped_xray(xray_id)
    if xray is None:
        return _error("X-ray not found.", 404)
    return jsonify({"data": _serialize_xray(xray)})


@xrays_blueprint.get("/x-rays/<int:xray_id>/file")
@login_required
@require_permission("xrays.read")
def get_xray_file(xray_id):
    xray = _scoped_xray(xray_id)
    if xray is None:
        return _error("X-ray not found.", 404)
    try:
        file_handle = _storage().open(xray.storage_key)
    except (FileNotFoundError, ValueError):
        return _error("X-ray file not found.", 404)

    response = send_file(
        file_handle,
        mimetype=xray.mime_type or "image/webp",
        as_attachment=False,
        download_name=xray.filename,
    )
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


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
    storage_key = xray.storage_key
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
    try:
        _storage().delete(storage_key)
    except (OSError, ValueError):
        current_app.logger.exception("Failed to clean up X-ray storage key %s", storage_key)
    return "", 204