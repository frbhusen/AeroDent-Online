from datetime import date
from decimal import Decimal, InvalidOperation

from flask import Blueprint, g, jsonify, request
from sqlalchemy.exc import IntegrityError

from backend.auth import login_required, require_permission
from backend.extensions import db
from backend.models import Invoice, Patient, Treatment, User
from backend.services.audit import log_activity


treatments_blueprint = Blueprint("treatments", __name__, url_prefix="/api/treatments")

TREATMENT_FIELDS = frozenset(
    {
        "patient_id",
        "doctor_id",
        "tooth_number",
        "status",
        "fee",
        "description",
        "procedure",
        "date",
    }
)
TREATMENT_INTERNAL_FIELDS = frozenset(
    {"id", "clinic_id", "created_by", "created_at", "updated_at"}
)
TREATMENT_STATUSES = frozenset(
    {"planned", "accepted", "scheduled", "in-progress", "completed", "cancelled"}
)
ELIGIBLE_DOCTOR_ROLES = frozenset({"head_doctor", "doctor"})
DEFAULT_PER_PAGE = 25
MAX_PER_PAGE = 100


def _error(message, status):
    return jsonify({"error": message}), status


def _json_object():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return None, _error("Request body must be a JSON object.", 400)

    unsupported = set(data) - TREATMENT_FIELDS
    if unsupported:
        if unsupported & TREATMENT_INTERNAL_FIELDS:
            return None, _error(
                "Treatment ownership fields are server-controlled.", 400
            )
        return None, _error("Unsupported treatment field.", 400)

    return data, None


def _parse_date(value):
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _parse_treatment_fields(data, *, partial):
    if "status" in data:
        if not isinstance(data["status"], str) or data["status"] not in TREATMENT_STATUSES:
            return None, _error("Invalid treatment status.", 400)

    if "date" in data:
        parsed_date = _parse_date(data["date"])
        if parsed_date is None:
            return None, _error("date must be an ISO date.", 422)
        data["date"] = parsed_date

    if "fee" in data:
        try:
            fee = Decimal(str(data["fee"]))
        except (InvalidOperation, TypeError, ValueError):
            return None, _error("fee must be a valid non-negative number.", 422)
        if not fee.is_finite() or fee < 0:
            return None, _error("fee must be a valid non-negative number.", 422)
        if fee > Decimal("99999999.99"):
            return None, _error("fee exceeds maximum allowable amount.", 422)
        data["fee"] = fee

    if "tooth_number" in data and data["tooth_number"] is not None:
        if (
            isinstance(data["tooth_number"], bool)
            or not isinstance(data["tooth_number"], int)
            or not 1 <= data["tooth_number"] <= 32
        ):
            return None, _error("Invalid tooth number.", 400)

    for field in ("patient_id", "doctor_id"):
        if field in data and data[field] is not None:
            if (
                isinstance(data[field], bool)
                or not isinstance(data[field], int)
                or data[field] <= 0
            ):
                return None, _error(f"{field} must be a positive integer.", 422)

    for field in ("description", "procedure"):
        if field in data and data[field] is not None:
            if not isinstance(data[field], str):
                return None, _error(f"{field} must be a string or null.", 422)
            if field == "procedure" and len(data[field]) > 150:
                return None, _error("procedure is too long.", 422)

    if not partial and "date" not in data:
        data["date"] = date.today()
    if not partial and "status" not in data:
        data["status"] = "planned"
    if not partial and "fee" not in data:
        data["fee"] = Decimal("0.00")

    return data, None


def _scoped_treatment(treatment_id):
    return db.session.scalar(
        db.select(Treatment).where(
            Treatment.id == treatment_id,
            Treatment.clinic_id == g.current_user.clinic_id,
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


def _serialize_treatment(treatment):
    return {
        "id": treatment.id,
        "clinic_id": treatment.clinic_id,
        "patient_id": treatment.patient_id,
        "doctor_id": treatment.doctor_id,
        "tooth_number": treatment.tooth_number,
        "status": treatment.status,
        "fee": format(treatment.fee, ".2f"),
        "description": treatment.description,
        "procedure": treatment.procedure,
        "date": treatment.date.isoformat(),
        "created_by": treatment.created_by,
        "created_at": treatment.created_at.isoformat() if treatment.created_at else None,
        "updated_at": treatment.updated_at.isoformat() if treatment.updated_at else None,
    }


@treatments_blueprint.get("")
@login_required
@require_permission("treatments.read")
def list_treatments():
    query = db.select(Treatment).where(
        Treatment.clinic_id == g.current_user.clinic_id
    )

    for field, model_field in (
        ("patient_id", Treatment.patient_id),
        ("doctor_id", Treatment.doctor_id),
    ):
        if field in request.args:
            try:
                value = int(request.args[field])
            except ValueError:
                return _error(f"{field} must be a positive integer.", 400)
            if value <= 0:
                return _error(f"{field} must be a positive integer.", 400)
            query = query.where(model_field == value)

    if "status" in request.args:
        if request.args["status"] not in TREATMENT_STATUSES:
            return _error("Invalid treatment status.", 400)
        query = query.where(Treatment.status == request.args["status"])

    try:
        page = max(int(request.args.get("page", 1)), 1)
        per_page = min(
            max(int(request.args.get("per_page", DEFAULT_PER_PAGE)), 1),
            MAX_PER_PAGE,
        )
    except ValueError:
        return _error("page and per_page must be positive integers.", 400)

    total = db.session.scalar(
        db.select(db.func.count()).select_from(query.subquery())
    )
    pages = (total + per_page - 1) // per_page if total else 0
    treatments = db.session.scalars(
        query.order_by(Treatment.date.desc(), Treatment.id.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    ).all()

    return jsonify(
        {
            "data": [_serialize_treatment(treatment) for treatment in treatments],
            "meta": {
                "page": page,
                "per_page": per_page,
                "total": total,
                "pages": pages,
            },
        }
    )


@treatments_blueprint.get("/<int:treatment_id>")
@login_required
@require_permission("treatments.read")
def get_treatment(treatment_id):
    treatment = _scoped_treatment(treatment_id)
    if treatment is None:
        return _error("Treatment not found.", 404)

    return jsonify({"data": _serialize_treatment(treatment)})


def _validate_references(data):
    patient = _scoped_patient(data["patient_id"])
    if patient is None:
        return None, _error("Patient not found.", 404)

    if data.get("doctor_id") is not None:
        doctor = _scoped_doctor(data["doctor_id"])
        if doctor is None:
            return None, _error("Doctor not found.", 404)

    return patient, None


@treatments_blueprint.post("")
@login_required
@require_permission("treatments.create")
def create_treatment():
    data, error = _json_object()
    if error:
        return error

    data, error = _parse_treatment_fields(data, partial=False)
    if error:
        return error

    if "patient_id" not in data:
        return _error("patient_id is required.", 422)

    data.setdefault("doctor_id", g.current_user.id)
    _, error = _validate_references(data)
    if error:
        return error

    treatment = Treatment(
        **data,
        clinic_id=g.current_user.clinic_id,
        created_by=g.current_user.id,
    )
    db.session.add(treatment)
    try:
        db.session.flush()
        log_activity(
            action="treatment_created",
            resource_type="treatment",
            resource_id=treatment.id,
            clinic_id=treatment.clinic_id,
            details={
                "patient_id": treatment.patient_id,
                "procedure": treatment.procedure,
                "fee": str(treatment.fee),
                "tooth_number": treatment.tooth_number,
            },
        )
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return _error("Treatment could not be created.", 409)

    return jsonify({"data": _serialize_treatment(treatment)}), 201


@treatments_blueprint.patch("/<int:treatment_id>")
@login_required
@require_permission("treatments.update")
def update_treatment(treatment_id):
    treatment = _scoped_treatment(treatment_id)
    if treatment is None:
        return _error("Treatment not found.", 404)

    data, error = _json_object()
    if error:
        return error

    data, error = _parse_treatment_fields(data, partial=True)
    if error:
        return error
    if not data:
        return _error("At least one treatment field is required.", 400)

    reference_data = {
        "patient_id": data.get("patient_id", treatment.patient_id),
        "doctor_id": data.get("doctor_id", treatment.doctor_id),
    }
    _, error = _validate_references(reference_data)
    if error:
        return error

    for field, value in data.items():
        setattr(treatment, field, value)

    try:
        log_activity(
            action="treatment_updated",
            resource_type="treatment",
            resource_id=treatment.id,
            clinic_id=treatment.clinic_id,
            details={
                "patient_id": treatment.patient_id,
                "procedure": treatment.procedure,
                "fee": str(treatment.fee),
                "status": treatment.status,
            },
        )
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return _error("Treatment could not be updated.", 409)

    return jsonify({"data": _serialize_treatment(treatment)})


@treatments_blueprint.delete("/<int:treatment_id>")
@login_required
@require_permission("treatments.delete")
def delete_treatment(treatment_id):
    treatment = _scoped_treatment(treatment_id)
    if treatment is None:
        return _error("Treatment not found.", 404)

    if db.session.scalar(
        db.select(Invoice.id).where(
            Invoice.treatment_id == treatment.id,
            Invoice.clinic_id == g.current_user.clinic_id,
        )
    ) is not None:
        return _error(
            "Treatment cannot be deleted because it is referenced by an invoice.",
            409,
        )

    log_activity(
        action="treatment_deleted",
        resource_type="treatment",
        resource_id=treatment.id,
        clinic_id=treatment.clinic_id,
        details={
            "patient_id": treatment.patient_id,
            "procedure": treatment.procedure,
        },
    )
    db.session.delete(treatment)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return _error("Treatment could not be deleted.", 409)

    return "", 204