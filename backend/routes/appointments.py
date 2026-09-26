from datetime import date, datetime, time, timedelta

from flask import Blueprint, g, jsonify, request
from sqlalchemy import and_, func, or_, text
from sqlalchemy.exc import IntegrityError

from backend.auth import login_required, require_permission
from backend.extensions import db
from backend.models import Appointment, Patient, User
from backend.services.audit import log_activity


appointments_blueprint = Blueprint(
    "appointments",
    __name__,
    url_prefix="/api/appointments",
)

APPOINTMENT_FIELDS = frozenset(
    {
        "patient_id",
        "doctor_id",
        "date",
        "start_time",
        "duration",
        "status",
        "procedure",
        "notes",
    }
)
APPOINTMENT_INTERNAL_FIELDS = frozenset(
    {"id", "clinic_id", "created_by", "created_at", "updated_at"}
)
APPOINTMENT_STATUSES = frozenset({"booked", "arrived", "in_chair", "completed", "cancelled"})
ELIGIBLE_DOCTOR_ROLES = frozenset({"head_doctor", "doctor"})
DEFAULT_PER_PAGE = 25
MAX_PER_PAGE = 100
MAX_DATE_RANGE_DAYS = 31


def _error(message, status):
    return jsonify({"error": message}), status


def _json_object():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return None, _error("Request body must be a JSON object.", 400)

    unsupported = set(data) - APPOINTMENT_FIELDS
    if unsupported:
        if unsupported & APPOINTMENT_INTERNAL_FIELDS:
            return None, _error(
                "Appointment ownership fields are server-controlled.", 400
            )
        return None, _error("Unsupported appointment field.", 400)

    return data, None


def _parse_date(value):
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _parse_time(value):
    if not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value, "%H:%M").time()
    except ValueError:
        return None


def _parse_fields(data):
    if "date" in data:
        parsed_date = _parse_date(data["date"])
        if parsed_date is None:
            return None, _error("date must be an ISO date.", 422)
        data["date"] = parsed_date

    if "start_time" in data:
        parsed_time = _parse_time(data["start_time"])
        if parsed_time is None:
            return None, _error("start_time must use HH:MM format.", 422)
        data["start_time"] = parsed_time

    if "duration" in data:
        if (
            isinstance(data["duration"], bool)
            or not isinstance(data["duration"], int)
            or data["duration"] <= 0
        ):
            return None, _error("duration must be a positive integer.", 422)

    if "status" in data:
        if data["status"] not in APPOINTMENT_STATUSES:
            return None, _error("Invalid appointment status.", 400)

    for field in ("patient_id", "doctor_id"):
        if field in data and data[field] is not None:
            if (
                isinstance(data[field], bool)
                or not isinstance(data[field], int)
                or data[field] <= 0
            ):
                return None, _error(f"{field} must be a positive integer.", 422)

    for field in ("procedure", "notes"):
        if field in data and data[field] is not None:
            if not isinstance(data[field], str):
                return None, _error(f"{field} must be a string or null.", 422)
            if field == "procedure" and len(data[field]) > 150:
                return None, _error("procedure is too long.", 422)

    return data, None


def _scoped_appointment(appointment_id):
    return db.session.scalar(
        db.select(Appointment).where(
            Appointment.id == appointment_id,
            Appointment.clinic_id == g.current_user.clinic_id,
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


def _serialize_appointment(appointment):
    return {
        "id": appointment.id,
        "clinic_id": appointment.clinic_id,
        "patient_id": appointment.patient_id,
        "doctor_id": appointment.doctor_id,
        "date": appointment.date.isoformat(),
        "start_time": appointment.start_time.strftime("%H:%M"),
        "duration": appointment.duration,
        "status": appointment.status,
        "procedure": appointment.procedure,
        "notes": appointment.notes,
        "created_by": appointment.created_by,
        "created_at": appointment.created_at.isoformat() if appointment.created_at else None,
        "updated_at": appointment.updated_at.isoformat() if appointment.updated_at else None,
    }


def _validate_references(data):
    if _scoped_patient(data["patient_id"]) is None:
        return _error("Patient not found.", 404)

    if data.get("doctor_id") is not None and _scoped_doctor(data["doctor_id"]) is None:
        return _error("Doctor not found.", 404)

    return None


def _working_hours_error(appointment_date, start_time, duration):
    clinic = g.current_clinic
    start_minutes = start_time.hour * 60 + start_time.minute
    end_minutes = start_minutes + duration
    work_start = clinic.work_start.hour * 60 + clinic.work_start.minute
    work_end = clinic.work_end.hour * 60 + clinic.work_end.minute
    if start_minutes < work_start or end_minutes > work_end:
        return _error("Appointment is outside clinic working hours.", 422)

    return None


def _has_conflict(appointment_date, doctor_id, start_time, duration, exclude_id=None):
    if doctor_id is None:
        return False

    new_end = (
        datetime.combine(appointment_date, start_time) + timedelta(minutes=duration)
    ).time()
    existing_end = Appointment.start_time + (
        Appointment.duration * text("INTERVAL '1 minute'")
    )
    query = db.select(Appointment.id).where(
        Appointment.clinic_id == g.current_user.clinic_id,
        Appointment.doctor_id == doctor_id,
        Appointment.date == appointment_date,
        Appointment.status != "cancelled",
        Appointment.start_time < new_end,
        existing_end > start_time,
    )
    if exclude_id is not None:
        query = query.where(Appointment.id != exclude_id)

    return db.session.scalar(query) is not None


@appointments_blueprint.get("")
@login_required
@require_permission("appointments.read")
def list_appointments():
    query = db.select(Appointment).where(
        Appointment.clinic_id == g.current_user.clinic_id
    )

    for field, model_field in (
        ("doctor_id", Appointment.doctor_id),
        ("patient_id", Appointment.patient_id),
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
        if request.args["status"] not in APPOINTMENT_STATUSES:
            return _error("Invalid appointment status.", 400)
        query = query.where(Appointment.status == request.args["status"])

    if "date" in request.args:
        requested_date = _parse_date(request.args["date"])
        if requested_date is None:
            return _error("date must be an ISO date.", 422)
        query = query.where(Appointment.date == requested_date)

    start_date = _parse_date(request.args["start_date"]) if "start_date" in request.args else None
    end_date = _parse_date(request.args["end_date"]) if "end_date" in request.args else None
    if "start_date" in request.args and start_date is None:
        return _error("start_date must be an ISO date.", 422)
    if "end_date" in request.args and end_date is None:
        return _error("end_date must be an ISO date.", 422)
    if start_date and end_date:
        if start_date > end_date:
            return _error("start_date must not be after end_date.", 400)
        if (end_date - start_date).days > MAX_DATE_RANGE_DAYS:
            return _error("Appointment date range is too large.", 400)
    if start_date:
        query = query.where(Appointment.date >= start_date)
    if end_date:
        query = query.where(Appointment.date <= end_date)

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
    appointments = db.session.scalars(
        query.order_by(Appointment.date, Appointment.start_time, Appointment.id)
        .offset((page - 1) * per_page)
        .limit(per_page)
    ).all()

    return jsonify(
        {
            "data": [_serialize_appointment(item) for item in appointments],
            "meta": {
                "page": page,
                "per_page": per_page,
                "total": total,
                "pages": pages,
            },
        }
    )


@appointments_blueprint.get("/<int:appointment_id>")
@login_required
@require_permission("appointments.read")
def get_appointment(appointment_id):
    appointment = _scoped_appointment(appointment_id)
    if appointment is None:
        return _error("Appointment not found.", 404)

    return jsonify({"data": _serialize_appointment(appointment)})


def _prepare_schedule(data, existing=None):
    clinic = g.current_clinic
    if existing is None:
        if "date" not in data or "start_time" not in data:
            return None, _error("date and start_time are required.", 422)
        data.setdefault("duration", clinic.slot_duration)
        data.setdefault("status", "booked")
        if g.current_user.role in ELIGIBLE_DOCTOR_ROLES:
            data.setdefault("doctor_id", g.current_user.id)
    else:
        for field, current_value in (
            ("patient_id", existing.patient_id),
            ("date", existing.date),
            ("start_time", existing.start_time),
            ("duration", existing.duration),
            ("status", existing.status),
            ("doctor_id", existing.doctor_id),
        ):
            data.setdefault(field, current_value)

    if data.get("duration") is None:
        data["duration"] = clinic.slot_duration
    if data.get("status") is None:
        data["status"] = "booked"
    if data.get("doctor_id") is None and g.current_user.role in ELIGIBLE_DOCTOR_ROLES:
        data["doctor_id"] = g.current_user.id

    error = _validate_references(data)
    if error:
        return None, error

    error = _working_hours_error(data["date"], data["start_time"], data["duration"])
    if error:
        return None, error

    if data["status"] != "cancelled" and _has_conflict(
        data["date"],
        data.get("doctor_id"),
        data["start_time"],
        data["duration"],
        existing.id if existing is not None else None,
    ):
        return None, _error("Appointment conflicts with an existing appointment.", 409)

    return data, None


@appointments_blueprint.post("")
@login_required
@require_permission("appointments.create")
def create_appointment():
    data, error = _json_object()
    if error:
        return error
    data, error = _parse_fields(data)
    if error:
        return error
    data, error = _prepare_schedule(data)
    if error:
        return error

    appointment = Appointment(
        **data,
        clinic_id=g.current_user.clinic_id,
        created_by=g.current_user.id,
    )
    db.session.add(appointment)
    try:
        db.session.flush()
        log_activity(
            action="appointment_created",
            resource_type="appointment",
            resource_id=appointment.id,
            clinic_id=appointment.clinic_id,
            details={
                "patient_id": appointment.patient_id,
                "date": str(appointment.date),
                "start_time": str(appointment.start_time),
                "procedure": appointment.procedure,
            },
        )
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return _error("Appointment could not be created.", 409)

    return jsonify({"data": _serialize_appointment(appointment)}), 201


@appointments_blueprint.patch("/<int:appointment_id>")
@login_required
@require_permission("appointments.update")
def update_appointment(appointment_id):
    appointment = _scoped_appointment(appointment_id)
    if appointment is None:
        return _error("Appointment not found.", 404)

    data, error = _json_object()
    if error:
        return error
    data, error = _parse_fields(data)
    if error:
        return error
    if not data:
        return _error("At least one appointment field is required.", 400)

    data, error = _prepare_schedule(data, appointment)
    if error:
        return error

    for field in APPOINTMENT_FIELDS:
        if field in data:
            setattr(appointment, field, data[field])

    try:
        log_activity(
            action="appointment_updated",
            resource_type="appointment",
            resource_id=appointment.id,
            clinic_id=appointment.clinic_id,
            details={
                "patient_id": appointment.patient_id,
                "status": appointment.status,
                "date": str(appointment.date),
                "start_time": str(appointment.start_time),
            },
        )
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return _error("Appointment could not be updated.", 409)

    return jsonify({"data": _serialize_appointment(appointment)})


@appointments_blueprint.delete("/<int:appointment_id>")
@login_required
@require_permission("appointments.delete")
def delete_appointment(appointment_id):
    appointment = _scoped_appointment(appointment_id)
    if appointment is None:
        return _error("Appointment not found.", 404)

    log_activity(
        action="appointment_deleted",
        resource_type="appointment",
        resource_id=appointment.id,
        clinic_id=appointment.clinic_id,
        details={
            "patient_id": appointment.patient_id,
            "date": str(appointment.date),
        },
    )
    db.session.delete(appointment)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return _error("Appointment could not be deleted.", 409)

    return "", 204