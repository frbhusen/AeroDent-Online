from decimal import Decimal, InvalidOperation

from flask import Blueprint, g, jsonify, request
from sqlalchemy.exc import IntegrityError

from backend.auth import login_required, require_permission
from backend.extensions import db
from backend.models import Patient, TreatmentPlan, User
from backend.services.audit import log_activity
from backend.services.validation import query_int, query_page


treatment_plans_blueprint = Blueprint(
    "treatment_plans",
    __name__,
    url_prefix="/api/treatment-plans",
)

TREATMENT_PLAN_FIELDS = frozenset(
    {
        "patient_id",
        "doctor_id",
        "tooth_number",
        "diagnosis",
        "procedure",
        "fee",
        "priority",
        "status",
        "notes",
    }
)
TREATMENT_PLAN_INTERNAL_FIELDS = frozenset(
    {"id", "clinic_id", "created_by", "created_at", "updated_at"}
)
TREATMENT_PLAN_PRIORITIES = frozenset({"low", "medium", "high"})
TREATMENT_PLAN_STATUSES = frozenset(
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

    unsupported = set(data) - TREATMENT_PLAN_FIELDS
    if unsupported:
        if unsupported & TREATMENT_PLAN_INTERNAL_FIELDS:
            return None, _error(
                "Treatment plan ownership fields are server-controlled.", 400
            )
        return None, _error("Unsupported treatment plan field.", 400)

    return data, None


def _parse_fields(data):
    if "priority" in data:
        if (
            not isinstance(data["priority"], str)
            or data["priority"] not in TREATMENT_PLAN_PRIORITIES
        ):
            return None, _error("Invalid treatment plan priority.", 400)

    if "status" in data:
        if (
            not isinstance(data["status"], str)
            or data["status"] not in TREATMENT_PLAN_STATUSES
        ):
            return None, _error("Invalid treatment plan status.", 400)

    if "fee" in data:
        try:
            fee = Decimal(str(data["fee"]))
        except (InvalidOperation, TypeError, ValueError):
            return None, _error("fee must be a valid non-negative number.", 422)
        if not fee.is_finite() or fee < 0:
            return None, _error("fee must be a valid non-negative number.", 422)
        data["fee"] = fee

    if "tooth_number" in data and data["tooth_number"] is not None:
        if (
            isinstance(data["tooth_number"], bool)
            or not isinstance(data["tooth_number"], int)
            or not 1 <= data["tooth_number"] <= 85
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

    for field in ("diagnosis", "procedure", "notes"):
        if field in data and data[field] is not None:
            if not isinstance(data[field], str):
                return None, _error(f"{field} must be a string or null.", 422)
            if field == "procedure" and len(data[field]) > 150:
                return None, _error("procedure is too long.", 422)

    return data, None


def _scoped_plan(plan_id):
    return db.session.scalar(
        db.select(TreatmentPlan).where(
            TreatmentPlan.id == plan_id,
            TreatmentPlan.clinic_id == g.current_user.clinic_id,
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


def _serialize_plan(plan):
    return {
        "id": plan.id,
        "clinic_id": plan.clinic_id,
        "patient_id": plan.patient_id,
        "doctor_id": plan.doctor_id,
        "tooth_number": plan.tooth_number,
        "diagnosis": plan.diagnosis,
        "procedure": plan.procedure,
        "fee": format(plan.fee, ".2f"),
        "priority": plan.priority,
        "status": plan.status,
        "notes": plan.notes,
        "created_by": plan.created_by,
        "created_at": plan.created_at.isoformat() if plan.created_at else None,
        "updated_at": plan.updated_at.isoformat() if plan.updated_at else None,
    }


def _validate_references(data):
    if _scoped_patient(data["patient_id"]) is None:
        return _error("Patient not found.", 404)

    if data.get("doctor_id") is not None and _scoped_doctor(data["doctor_id"]) is None:
        return _error("Doctor not found.", 404)

    return None


@treatment_plans_blueprint.get("")
@login_required
@require_permission("treatment_plans.read")
def list_treatment_plans():
    query = db.select(TreatmentPlan).where(
        TreatmentPlan.clinic_id == g.current_user.clinic_id
    )

    for field, model_field in (
        ("patient_id", TreatmentPlan.patient_id),
        ("doctor_id", TreatmentPlan.doctor_id),
    ):
        if field in request.args:
            try:
                value = query_int(request.args[field])
            except ValueError:
                return _error(f"{field} must be a positive integer.", 400)
            if value <= 0:
                return _error(f"{field} must be a positive integer.", 400)
            query = query.where(model_field == value)

    for field, allowed, model_field in (
        ("priority", TREATMENT_PLAN_PRIORITIES, TreatmentPlan.priority),
        ("status", TREATMENT_PLAN_STATUSES, TreatmentPlan.status),
    ):
        if field in request.args:
            if request.args[field] not in allowed:
                return _error(f"Invalid treatment plan {field}.", 400)
            query = query.where(model_field == request.args[field])

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
    plans = db.session.scalars(
        query.order_by(TreatmentPlan.id.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    ).all()

    return jsonify(
        {
            "data": [_serialize_plan(plan) for plan in plans],
            "meta": {
                "page": page,
                "per_page": per_page,
                "total": total,
                "pages": pages,
            },
        }
    )


@treatment_plans_blueprint.get("/<int:treatment_plan_id>")
@login_required
@require_permission("treatment_plans.read")
def get_treatment_plan(treatment_plan_id):
    plan = _scoped_plan(treatment_plan_id)
    if plan is None:
        return _error("Treatment plan not found.", 404)

    return jsonify({"data": _serialize_plan(plan)})


@treatment_plans_blueprint.post("")
@login_required
@require_permission("treatment_plans.create")
def create_treatment_plan():
    data, error = _json_object()
    if error:
        return error

    data, error = _parse_fields(data)
    if error:
        return error
    if "patient_id" not in data:
        return _error("patient_id is required.", 422)

    data.setdefault("doctor_id", g.current_user.id)
    error = _validate_references(data)
    if error:
        return error

    data.setdefault("fee", Decimal("0.00"))
    data.setdefault("priority", "medium")
    data.setdefault("status", "planned")
    plan = TreatmentPlan(
        **data,
        clinic_id=g.current_user.clinic_id,
        created_by=g.current_user.id,
    )
    db.session.add(plan)
    try:
        db.session.flush()
        log_activity(
            action="treatment_plan_created",
            resource_type="treatment_plan",
            resource_id=plan.id,
            clinic_id=plan.clinic_id,
            details={
                "patient_id": plan.patient_id,
                "procedure": plan.procedure,
                "fee": str(plan.fee),
                "priority": plan.priority,
            },
        )
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return _error("Treatment plan could not be created.", 409)

    return jsonify({"data": _serialize_plan(plan)}), 201


@treatment_plans_blueprint.patch("/<int:treatment_plan_id>")
@login_required
@require_permission("treatment_plans.update")
def update_treatment_plan(treatment_plan_id):
    plan = _scoped_plan(treatment_plan_id)
    if plan is None:
        return _error("Treatment plan not found.", 404)

    data, error = _json_object()
    if error:
        return error
    data, error = _parse_fields(data)
    if error:
        return error
    if not data:
        return _error("At least one treatment plan field is required.", 400)

    reference_data = {
        "patient_id": data.get("patient_id", plan.patient_id),
        "doctor_id": data.get("doctor_id", plan.doctor_id),
    }
    error = _validate_references(reference_data)
    if error:
        return error

    for field, value in data.items():
        setattr(plan, field, value)

    try:
        log_activity(
            action="treatment_plan_updated",
            resource_type="treatment_plan",
            resource_id=plan.id,
            clinic_id=plan.clinic_id,
            details={
                "patient_id": plan.patient_id,
                "procedure": plan.procedure,
                "status": plan.status,
            },
        )
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return _error("Treatment plan could not be updated.", 409)

    return jsonify({"data": _serialize_plan(plan)})


@treatment_plans_blueprint.delete("/<int:treatment_plan_id>")
@login_required
@require_permission("treatment_plans.delete")
def delete_treatment_plan(treatment_plan_id):
    plan = _scoped_plan(treatment_plan_id)
    if plan is None:
        return _error("Treatment plan not found.", 404)

    log_activity(
        action="treatment_plan_deleted",
        resource_type="treatment_plan",
        resource_id=plan.id,
        clinic_id=plan.clinic_id,
        details={
            "patient_id": plan.patient_id,
            "procedure": plan.procedure,
        },
    )
    db.session.delete(plan)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return _error("Treatment plan could not be deleted.", 409)

    return "", 204