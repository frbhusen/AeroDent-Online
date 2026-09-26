from flask import Blueprint, g, jsonify, request
from sqlalchemy.exc import IntegrityError

from backend.auth import login_required, require_permission
from backend.extensions import db
from backend.models import Odontogram, Patient
from backend.services.audit import log_activity


odontogram_blueprint = Blueprint(
    "odontogram",
    __name__,
    url_prefix="/api/patients",
)

VALID_TOOTH_MODES = frozenset({"permanent", "primary"})
TOOTH_RANGES = {
    "permanent": range(1, 33),
    "primary": range(1, 21),
}
ODONTOGRAM_FIELDS = frozenset({"condition", "procedure", "notes"})
ODONTOGRAM_IDENTITY_FIELDS = frozenset(
    {
        "id",
        "clinic_id",
        "patient_id",
        "tooth_number",
        "tooth_mode",
        "created_by",
        "created_at",
        "updated_at",
    }
)


def _error(message, status):
    return jsonify({"error": message}), status


def _scoped_patient(patient_id):
    return db.session.scalar(
        db.select(Patient).where(
            Patient.id == patient_id,
            Patient.clinic_id == g.current_user.clinic_id,
        )
    )


def _validate_tooth(tooth_mode, tooth_number):
    if not isinstance(tooth_mode, str) or tooth_mode not in VALID_TOOTH_MODES:
        return _error("Invalid tooth mode.", 400)

    if tooth_number not in TOOTH_RANGES[tooth_mode]:
        return _error("Invalid tooth number.", 400)

    return None


def _serialize_odontogram(record):
    return {
        "id": record.id,
        "tooth_number": record.tooth_number,
        "tooth_mode": record.tooth_mode,
        "condition": record.condition,
        "procedure": record.procedure,
        "notes": record.notes,
        "created_by": record.created_by,
        "created_at": record.created_at.isoformat() if record.created_at else None,
        "updated_at": record.updated_at.isoformat() if record.updated_at else None,
    }


def _json_object():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return None, _error("Request body must be a JSON object.", 400)

    unsupported = set(data) - ODONTOGRAM_FIELDS
    if unsupported:
        if unsupported & ODONTOGRAM_IDENTITY_FIELDS:
            return None, _error(
                "Odontogram identity fields are server-controlled.", 400
            )
        return None, _error("Unsupported odontogram field.", 400)

    for field, value in data.items():
        if value is not None and not isinstance(value, str):
            return None, _error(f"{field} must be a string or null.", 422)

    return data, None


def _scoped_record(patient_id, tooth_mode, tooth_number):
    return db.session.scalar(
        db.select(Odontogram).where(
            Odontogram.patient_id == patient_id,
            Odontogram.clinic_id == g.current_user.clinic_id,
            Odontogram.tooth_mode == tooth_mode,
            Odontogram.tooth_number == tooth_number,
        )
    )


@odontogram_blueprint.get("/<int:patient_id>/odontogram")
@login_required
@require_permission("odontogram.read")
def list_odontogram(patient_id):
    patient = _scoped_patient(patient_id)
    if patient is None:
        return _error("Patient not found.", 404)

    mode = request.args.get("mode")
    if mode is not None and (not isinstance(mode, str) or mode not in VALID_TOOTH_MODES):
        return _error("Invalid tooth mode.", 400)

    query = db.select(Odontogram).where(
        Odontogram.patient_id == patient.id,
        Odontogram.clinic_id == g.current_user.clinic_id,
    )
    if mode is not None:
        query = query.where(Odontogram.tooth_mode == mode)

    records = db.session.scalars(
        query.order_by(Odontogram.tooth_mode, Odontogram.tooth_number)
    ).all()

    return jsonify(
        {
            "data": [_serialize_odontogram(record) for record in records],
            "meta": {"patient_id": patient.id, "count": len(records)},
        }
    )


@odontogram_blueprint.put(
    "/<int:patient_id>/odontogram/<string:tooth_mode>/<int:tooth_number>"
)
@login_required
@require_permission("odontogram.update")
def upsert_odontogram(patient_id, tooth_mode, tooth_number):
    patient = _scoped_patient(patient_id)
    if patient is None:
        return _error("Patient not found.", 404)

    validation_error = _validate_tooth(tooth_mode, tooth_number)
    if validation_error:
        return validation_error

    data, error = _json_object()
    if error:
        return error

    record = _scoped_record(patient.id, tooth_mode, tooth_number)
    created = record is None
    if created:
        record = Odontogram(
            clinic_id=g.current_user.clinic_id,
            patient_id=patient.id,
            tooth_mode=tooth_mode,
            tooth_number=tooth_number,
            created_by=g.current_user.id,
        )
        db.session.add(record)

    for field, value in data.items():
        setattr(record, field, value)

    try:
        log_activity(
            action="odontogram_updated",
            resource_type="odontogram",
            resource_id=record.id,
            clinic_id=record.clinic_id,
            details={
                "patient_id": patient.id,
                "tooth_number": tooth_number,
                "tooth_mode": tooth_mode,
                "condition": record.condition,
                "procedure": record.procedure,
            },
        )
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return _error("Odontogram could not be saved.", 409)

    return jsonify({"data": _serialize_odontogram(record)}), 201 if created else 200


@odontogram_blueprint.delete(
    "/<int:patient_id>/odontogram/<string:tooth_mode>/<int:tooth_number>"
)
@login_required
@require_permission("odontogram.update")
def delete_odontogram(patient_id, tooth_mode, tooth_number):
    patient = _scoped_patient(patient_id)
    if patient is None:
        return _error("Patient not found.", 404)

    validation_error = _validate_tooth(tooth_mode, tooth_number)
    if validation_error:
        return validation_error

    record = _scoped_record(patient.id, tooth_mode, tooth_number)
    if record is None:
        return _error("Odontogram record not found.", 404)

    db.session.delete(record)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return _error("Odontogram could not be deleted.", 409)

    return "", 204