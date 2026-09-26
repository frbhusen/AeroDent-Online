from datetime import date

from flask import Blueprint, g, jsonify, request
from sqlalchemy.exc import IntegrityError

from backend.auth import login_required, require_permission
from backend.extensions import db
from backend.models import Patient, Prescription, PrescriptionMedication, User
from backend.services.audit import log_activity
from backend.services.validation import query_int, query_page


prescriptions_blueprint = Blueprint(
    "prescriptions",
    __name__,
    url_prefix="/api/prescriptions",
)

PRESCRIPTION_FIELDS = frozenset({"patient_id", "doctor_id", "date", "notes", "medications"})
PRESCRIPTION_INTERNAL_FIELDS = frozenset(
    {"id", "clinic_id", "created_by", "created_at", "updated_at"}
)
MEDICATION_FIELDS = frozenset({"name", "dosage", "frequency", "duration", "instructions"})
ELIGIBLE_DOCTOR_ROLES = frozenset({"head_doctor", "doctor"})
DEFAULT_PER_PAGE = 25
MAX_PER_PAGE = 100
MAX_MEDICATIONS = 100
# Mirrors the column sizes on PrescriptionMedication.
MEDICATION_FIELD_LIMITS = {"name": 200, "dosage": 100, "frequency": 100, "duration": 100, "instructions": 2000}


def _error(message, status):
    return jsonify({"error": message}), status


def _json_object():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return None, _error("Request body must be a JSON object.", 400)

    unsupported = set(data) - PRESCRIPTION_FIELDS
    if unsupported:
        if unsupported & PRESCRIPTION_INTERNAL_FIELDS:
            return None, _error(
                "Prescription ownership fields are server-controlled.", 400
            )
        return None, _error("Unsupported prescription field.", 400)

    return data, None


def _parse_date(value):
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _scoped_prescription(prescription_id):
    return db.session.scalar(
        db.select(Prescription).where(
            Prescription.id == prescription_id,
            Prescription.clinic_id == g.current_user.clinic_id,
        )
    )


def _scoped_patient(patient_id):
    return db.session.scalar(
        db.select(Patient).where(
            Patient.id == patient_id,
            Patient.clinic_id == g.current_user.clinic_id,
        )
    )


def _scoped_doctor(doctor_id):
    return db.session.scalar(
        db.select(User).where(
            User.id == doctor_id,
            User.clinic_id == g.current_user.clinic_id,
            User.is_active.is_(True),
            User.role.in_(ELIGIBLE_DOCTOR_ROLES),
        )
    )


def _validate_medications(value):
    if not isinstance(value, list) or not value:
        return None, _error("medications must contain at least one item.", 422)
    if len(value) > MAX_MEDICATIONS:
        return None, _error("Too many medications.", 422)

    normalized = []
    for medication in value:
        if not isinstance(medication, dict):
            return None, _error("Each medication must be an object.", 422)
        unsupported = set(medication) - MEDICATION_FIELDS
        if unsupported:
            return None, _error("Unsupported medication field.", 400)
        if not isinstance(medication.get("name"), str) or not medication["name"].strip():
            return None, _error("Medication name is required.", 422)
        if len(medication["name"].strip()) > MEDICATION_FIELD_LIMITS["name"]:
            return None, _error("Medication name is too long.", 422)

        item = {"name": medication["name"].strip()}
        for field in MEDICATION_FIELDS - {"name"}:
            value = medication.get(field)
            if value is not None and not isinstance(value, str):
                return None, _error(f"Medication {field} must be a string or null.", 422)
            limit = MEDICATION_FIELD_LIMITS.get(field)
            if isinstance(value, str) and limit and len(value) > limit:
                return None, _error(f"Medication {field} is too long (maximum {limit} characters).", 422)
            item[field] = value
        normalized.append(item)

    return normalized, None


def _parse_fields(data):
    if "date" in data:
        parsed_date = _parse_date(data["date"])
        if parsed_date is None:
            return None, _error("date must be an ISO date.", 422)
        data["date"] = parsed_date

    for field in ("patient_id", "doctor_id"):
        if field in data and data[field] is not None:
            if (
                isinstance(data[field], bool)
                or not isinstance(data[field], int)
                or data[field] <= 0
            ):
                return None, _error(f"{field} must be a positive integer.", 422)

    if "notes" in data and data["notes"] is not None and not isinstance(data["notes"], str):
        return None, _error("notes must be a string or null.", 422)

    if "medications" in data:
        medications, error = _validate_medications(data["medications"])
        if error:
            return None, error
        data["medications"] = medications

    return data, None


def _serialize_medication(medication):
    return {
        "id": medication.id,
        "name": medication.name,
        "dosage": medication.dosage,
        "frequency": medication.frequency,
        "duration": medication.duration,
        "instructions": medication.instructions,
    }


def _serialize_prescription(prescription, include_medications=False):
    data = {
        "id": prescription.id,
        "clinic_id": prescription.clinic_id,
        "patient_id": prescription.patient_id,
        "doctor_id": prescription.doctor_id,
        "date": prescription.date.isoformat(),
        "notes": prescription.notes,
        "created_by": prescription.created_by,
        "created_at": prescription.created_at.isoformat() if prescription.created_at else None,
        "updated_at": prescription.updated_at.isoformat() if prescription.updated_at else None,
    }
    if include_medications:
        data["medications"] = [
            _serialize_medication(item) for item in prescription.medications
        ]
    return data


def _validate_references(data):
    if _scoped_patient(data["patient_id"]) is None:
        return _error("Patient not found.", 404)
    if data.get("doctor_id") is not None and _scoped_doctor(data["doctor_id"]) is None:
        return _error("Doctor not found.", 404)
    return None


@prescriptions_blueprint.get("")
@login_required
@require_permission("prescriptions.read")
def list_prescriptions():
    query = db.select(Prescription).where(
        Prescription.clinic_id == g.current_user.clinic_id
    )
    for field, model_field in (
        ("patient_id", Prescription.patient_id),
        ("doctor_id", Prescription.doctor_id),
    ):
        if field in request.args:
            try:
                value = query_int(request.args[field])
            except ValueError:
                return _error(f"{field} must be a positive integer.", 400)
            if value <= 0:
                return _error(f"{field} must be a positive integer.", 400)
            query = query.where(model_field == value)

    if "date" in request.args:
        requested_date = _parse_date(request.args["date"])
        if requested_date is None:
            return _error("date must be an ISO date.", 422)
        query = query.where(Prescription.date == requested_date)

    try:
        page = max(query_page(request.args.get("page", 1)), 1)
        per_page = min(
            max(query_int(request.args.get("per_page", DEFAULT_PER_PAGE)), 1),
            MAX_PER_PAGE,
        )
    except ValueError:
        return _error("page and per_page must be positive integers.", 400)

    total = db.session.scalar(db.select(db.func.count()).select_from(query.subquery()))
    pages = (total + per_page - 1) // per_page if total else 0
    prescriptions = db.session.scalars(
        query.order_by(Prescription.date.desc(), Prescription.id.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    ).all()

    return jsonify(
        {
            "data": [_serialize_prescription(item) for item in prescriptions],
            "meta": {"page": page, "per_page": per_page, "total": total, "pages": pages},
        }
    )


@prescriptions_blueprint.get("/<int:prescription_id>")
@login_required
@require_permission("prescriptions.read")
def get_prescription(prescription_id):
    prescription = _scoped_prescription(prescription_id)
    if prescription is None:
        return _error("Prescription not found.", 404)
    return jsonify({"data": _serialize_prescription(prescription, True)})


def _apply_medications(prescription, medications):
    prescription.medications.clear()
    prescription.medications.extend(
        PrescriptionMedication(**medication) for medication in medications
    )


@prescriptions_blueprint.post("")
@login_required
@require_permission("prescriptions.create")
def create_prescription():
    data, error = _json_object()
    if error:
        return error
    data, error = _parse_fields(data)
    if error:
        return error
    if "patient_id" not in data or "date" not in data:
        return _error("patient_id and date are required.", 422)
    if "medications" not in data:
        return _error("medications are required.", 422)

    data.setdefault("doctor_id", g.current_user.id)
    error = _validate_references(data)
    if error:
        return error
    medications = data.pop("medications")
    prescription = Prescription(
        **data,
        clinic_id=g.current_user.clinic_id,
        created_by=g.current_user.id,
    )
    _apply_medications(prescription, medications)
    db.session.add(prescription)
    try:
        db.session.flush()
        log_activity(
            action="prescription_created",
            resource_type="prescription",
            resource_id=prescription.id,
            clinic_id=prescription.clinic_id,
            details={
                "patient_id": prescription.patient_id,
                "date": str(prescription.date),
                "medications_count": len(prescription.medications),
            },
        )
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return _error("Prescription could not be created.", 409)

    return jsonify({"data": _serialize_prescription(prescription, True)}), 201


@prescriptions_blueprint.patch("/<int:prescription_id>")
@login_required
@require_permission("prescriptions.update")
def update_prescription(prescription_id):
    prescription = _scoped_prescription(prescription_id)
    if prescription is None:
        return _error("Prescription not found.", 404)

    data, error = _json_object()
    if error:
        return error
    data, error = _parse_fields(data)
    if error:
        return error
    if not data:
        return _error("At least one prescription field is required.", 400)

    references = {
        "patient_id": data.get("patient_id", prescription.patient_id),
        "doctor_id": data.get("doctor_id", prescription.doctor_id),
    }
    error = _validate_references(references)
    if error:
        return error

    medications = data.pop("medications", None)
    for field, value in data.items():
        setattr(prescription, field, value)
    if medications is not None:
        _apply_medications(prescription, medications)

    try:
        log_activity(
            action="prescription_updated",
            resource_type="prescription",
            resource_id=prescription.id,
            clinic_id=prescription.clinic_id,
            details={
                "patient_id": prescription.patient_id,
                "date": str(prescription.date),
            },
        )
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return _error("Prescription could not be updated.", 409)

    return jsonify({"data": _serialize_prescription(prescription, True)})


@prescriptions_blueprint.delete("/<int:prescription_id>")
@login_required
@require_permission("prescriptions.delete")
def delete_prescription(prescription_id):
    prescription = _scoped_prescription(prescription_id)
    if prescription is None:
        return _error("Prescription not found.", 404)

    log_activity(
        action="prescription_deleted",
        resource_type="prescription",
        resource_id=prescription.id,
        clinic_id=prescription.clinic_id,
        details={
            "patient_id": prescription.patient_id,
        },
    )
    db.session.delete(prescription)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return _error("Prescription could not be deleted.", 409)

    return "", 204