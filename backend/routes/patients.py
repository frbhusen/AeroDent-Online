from datetime import date

from flask import Blueprint, g, jsonify, request
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError

from backend.auth import login_required, require_permission, validate_patient_update
from backend.extensions import db
from backend.models import Patient
from backend.services.audit import log_activity
from backend.services.validation import query_int, query_page


patients_blueprint = Blueprint("patients", __name__, url_prefix="/api/patients")

PATIENT_FIELDS = frozenset(
    {
        "name",
        "phone",
        "location",
        "work_study",
        "dob",
        "gender",
        "allergies",
        "medical_flags",
        "notes",
    }
)

PATIENT_INTERNAL_FIELDS = frozenset(
    {
        "id",
        "clinic_id",
        "created_by",
        "created_at",
        "updated_at",
    }
)

DEFAULT_PER_PAGE = 25
MAX_PER_PAGE = 100


def _error(message, status):
    return jsonify({"error": message}), status


def _serialize_patient(patient):
    return {
        "id": patient.id,
        "clinic_id": patient.clinic_id,
        "name": patient.name,
        "phone": patient.phone,
        "location": patient.location,
        "work_study": patient.work_study,
        "dob": patient.dob.isoformat() if patient.dob else None,
        "gender": patient.gender,
        "allergies": patient.allergies,
        "medical_flags": patient.medical_flags,
        "notes": patient.notes,
        "created_by": patient.created_by,
        "created_at": patient.created_at.isoformat() if patient.created_at else None,
        "updated_at": patient.updated_at.isoformat() if patient.updated_at else None,
    }


def _json_object():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return None, _error("Request body must be a JSON object.", 400)

    return data, None


def _parse_patient_fields(data, *, partial):
    unsupported = set(data) - PATIENT_FIELDS
    if unsupported:
        return None, _error("Unsupported patient field.", 400)

    if not partial and (not isinstance(data.get("name"), str) or not data["name"].strip()):
        return None, _error("Patient name is required.", 422)

    if "name" in data:
        if not isinstance(data["name"], str) or not data["name"].strip():
            return None, _error("Patient name must not be blank.", 422)
        if len(data["name"].strip()) > 200:
            return None, _error("Patient name is too long (maximum 200 characters).", 422)
        data["name"] = data["name"].strip()

    if "dob" in data and data["dob"] is not None:
        if not isinstance(data["dob"], str):
            return None, _error("dob must be an ISO date.", 422)
        val = data["dob"].strip()
        if not val:
            data["dob"] = None
        else:
            try:
                data["dob"] = date.fromisoformat(val)
            except ValueError:
                return None, _error("dob must be an ISO date.", 422)

    field_limits = {
        "phone": 50,
        "location": 200,
        "work_study": 200,
        "gender": 20,
    }

    for field in PATIENT_FIELDS - {"name", "dob"}:
        if field in data and data[field] is not None:
            if not isinstance(data[field], str):
                return None, _error(f"{field} must be a string or null.", 422)
            stripped = data[field].strip()
            max_len = field_limits.get(field)
            if max_len and len(stripped) > max_len:
                return None, _error(f"{field} is too long (maximum {max_len} characters).", 422)
            data[field] = stripped or None

    return data, None


def _scoped_patient(patient_id):
    return db.session.scalar(
        db.select(Patient).where(
            Patient.id == patient_id,
            Patient.clinic_id == g.current_user.clinic_id,
        )
    )


@patients_blueprint.get("")
@login_required
@require_permission("patients.read")
def list_patients():
    query = db.select(Patient).where(Patient.clinic_id == g.current_user.clinic_id)

    search = request.args.get("q", "").strip()[:100]
    if search:
        pattern = f"%{search}%"
        query = query.where(
            or_(Patient.name.ilike(pattern), Patient.phone.ilike(pattern))
        )

    try:
        page = max(query_page(request.args.get("page", 1)), 1)
        per_page = min(
            max(query_int(request.args.get("per_page", DEFAULT_PER_PAGE)), 1),
            MAX_PER_PAGE,
        )
    except ValueError:
        return _error("page and per_page must be positive integers.", 400)

    total = db.session.scalar(
        db.select(db.func.count()).select_from(query.subquery())
    )
    pages = (total + per_page - 1) // per_page if total else 0
    patients = db.session.scalars(
        query.order_by(Patient.id).offset((page - 1) * per_page).limit(per_page)
    ).all()

    return jsonify(
        {
            "data": [_serialize_patient(patient) for patient in patients],
            "meta": {
                "page": page,
                "per_page": per_page,
                "total": total,
                "pages": pages,
            },
        }
    )


@patients_blueprint.get("/<int:patient_id>")
@login_required
@require_permission("patients.read")
def get_patient(patient_id):
    patient = _scoped_patient(patient_id)
    if patient is None:
        return _error("Patient not found.", 404)

    return jsonify({"data": _serialize_patient(patient)})


@patients_blueprint.post("")
@login_required
@require_permission("patients.create")
def create_patient():
    data, error = _json_object()
    if error or data is None:
        return error or _error("Request body must be a JSON object.", 400)

    forbidden = set(data) & PATIENT_INTERNAL_FIELDS
    if forbidden:
        return _error("Patient ownership fields are server-controlled.", 400)

    data, error = _parse_patient_fields(data, partial=False)
    if error or data is None:
        return error or _error("Invalid patient data.", 400)

    if g.current_user.role == "secretary":
        for cf in ("allergies", "medical_flags", "notes"):
            data.pop(cf, None)

    patient = Patient(
        **data,
        clinic_id=g.current_user.clinic_id,
        created_by=g.current_user.id,
    )
    db.session.add(patient)
    try:
        db.session.flush()
        log_activity(
            action="patient_created",
            resource_type="patient",
            resource_id=patient.id,
            details={"name": patient.name, "phone": patient.phone},
        )
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return _error("Patient could not be created.", 409)

    return jsonify({"data": _serialize_patient(patient)}), 201


@patients_blueprint.patch("/<int:patient_id>")
@login_required
@require_permission("patients.update")
def update_patient(patient_id):
    patient = _scoped_patient(patient_id)
    if patient is None:
        return _error("Patient not found.", 404)

    data, error = _json_object()
    if error or data is None:
        return error or _error("Request body must be a JSON object.", 400)

    if set(data) & PATIENT_INTERNAL_FIELDS:
        return _error("Patient ownership fields are server-controlled.", 400)

    data, error = _parse_patient_fields(data, partial=True)
    if error or data is None:
        return error or _error("Invalid patient data.", 400)

    try:
        validate_patient_update(g.current_user, data)
    except PermissionError:
        return _error("You do not have permission to update these patient fields.", 403)

    if not data:
        return _error("At least one patient field is required.", 400)

    for field, value in data.items():
        setattr(patient, field, value)

    try:
        log_activity(
            action="patient_updated",
            resource_type="patient",
            resource_id=patient.id,
            details={"name": patient.name, "fields": list(data.keys())},
        )
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return _error("Patient could not be updated.", 409)

    return jsonify({"data": _serialize_patient(patient)})


@patients_blueprint.delete("/<int:patient_id>")
@login_required
@require_permission("patients.delete")
def delete_patient(patient_id):
    patient = _scoped_patient(patient_id)
    if patient is None:
        return _error("Patient not found.", 404)

    patient_name = patient.name
    patient_id_val = patient.id
    db.session.delete(patient)
    try:
        log_activity(
            action="patient_deleted",
            resource_type="patient",
            resource_id=patient_id_val,
            details={"name": patient_name},
        )
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return _error("Patient could not be deleted.", 409)

    return "", 204