from datetime import date, datetime, time
from flask import Blueprint, g, jsonify, request
from sqlalchemy import case, desc

from backend.auth import login_required, require_permission
from backend.extensions import db
from backend.models import Appointment, Patient, User, Waitlist
from backend.services.audit import log_activity


waitlist_blueprint = Blueprint("waitlist", __name__, url_prefix="/api/waitlist")

WAITLIST_FIELDS = frozenset(
    {
        "patient_id",
        "doctor_id",
        "preferred_date",
        "preferred_time",
        "procedure",
        "priority",
        "status",
        "notes",
    }
)
WAITLIST_PRIORITIES = frozenset({"normal", "high", "urgent"})
WAITLIST_STATUSES = frozenset({"waiting", "booked", "cancelled"})


def _error(message, status):
    return jsonify({"error": message}), status


def _scoped_waitlist(entry_id):
    return db.session.scalar(
        db.select(Waitlist).where(
            Waitlist.id == entry_id,
            Waitlist.clinic_id == g.current_user.clinic_id,
        )
    )


def _serialize_waitlist(item):
    return {
        "id": item.id,
        "clinic_id": item.clinic_id,
        "patient_id": item.patient_id,
        "patient_name": item.patient.name if item.patient else f"Patient #{item.patient_id}",
        "patient_phone": item.patient.phone if item.patient else "",
        "doctor_id": item.doctor_id,
        "doctor_name": item.doctor.name if item.doctor else "",
        "preferred_date": item.preferred_date.isoformat() if item.preferred_date else None,
        "preferred_time": item.preferred_time or "",
        "procedure": item.procedure or "",
        "priority": item.priority,
        "status": item.status,
        "notes": item.notes or "",
        "created_by": item.created_by,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
    }


@waitlist_blueprint.get("")
@login_required
@require_permission("appointments.read")
def list_waitlist():
    query = (
        db.select(Waitlist)
        .where(Waitlist.clinic_id == g.current_user.clinic_id)
        .join(Waitlist.patient)
    )

    status = request.args.get("status", "waiting")
    if status and status != "all":
        query = query.where(Waitlist.status == status)

    if "patient_id" in request.args:
        try:
            query = query.where(Waitlist.patient_id == int(request.args["patient_id"]))
        except ValueError:
            return _error("patient_id must be an integer.", 400)

    # Order: urgent first, then high, then normal; then by created_at ascending
    priority_order = case(
        (Waitlist.priority == "urgent", 1),
        (Waitlist.priority == "high", 2),
        else_=3,
    )
    query = query.order_by(priority_order, Waitlist.created_at.asc())

    records = db.session.scalars(query).all()
    return jsonify({"data": [_serialize_waitlist(item) for item in records], "meta": {"count": len(records)}})


@waitlist_blueprint.post("")
@login_required
@require_permission("appointments.create")
def create_waitlist_entry():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return _error("Request body must be a JSON object.", 400)

    patient_id = data.get("patient_id")
    if not isinstance(patient_id, int):
        return _error("patient_id is required and must be an integer.", 400)

    # Validate patient belongs to this clinic
    patient = db.session.scalar(
        db.select(Patient).where(
            Patient.id == patient_id,
            Patient.clinic_id == g.current_user.clinic_id,
        )
    )
    if not patient:
        return _error("Patient not found.", 404)

    doctor_id = data.get("doctor_id")
    if doctor_id is not None:
        if not isinstance(doctor_id, int):
            return _error("doctor_id must be an integer.", 400)
        doctor = db.session.scalar(
            db.select(User).where(
                User.id == doctor_id,
                User.clinic_id == g.current_user.clinic_id,
            )
        )
        if not doctor:
            return _error("Doctor not found.", 404)

    preferred_date = None
    if data.get("preferred_date"):
        try:
            preferred_date = date.fromisoformat(data["preferred_date"])
        except (ValueError, TypeError):
            return _error("preferred_date must be an ISO date (YYYY-MM-DD).", 422)

    priority = data.get("priority", "normal")
    if priority not in WAITLIST_PRIORITIES:
        return _error("priority must be one of: normal, high, urgent.", 422)

    entry = Waitlist(
        clinic_id=g.current_user.clinic_id,
        patient_id=patient_id,
        doctor_id=doctor_id,
        preferred_date=preferred_date,
        preferred_time=str(data.get("preferred_time") or "").strip() or None,
        procedure=str(data.get("procedure") or "").strip() or None,
        priority=priority,
        status="waiting",
        notes=str(data.get("notes") or "").strip() or None,
        created_by=g.current_user.id,
    )
    db.session.add(entry)
    db.session.flush()

    log_activity(
        action="waitlist_created",
        resource_type="waitlist",
        resource_id=entry.id,
        clinic_id=entry.clinic_id,
        details={
            "patient_id": entry.patient_id,
            "patient_name": patient.name,
            "priority": entry.priority,
            "procedure": entry.procedure,
        },
    )
    db.session.commit()

    return jsonify({"data": _serialize_waitlist(entry)}), 201


@waitlist_blueprint.patch("/<int:entry_id>")
@login_required
@require_permission("appointments.update")
def update_waitlist_entry(entry_id):
    entry = _scoped_waitlist(entry_id)
    if not entry:
        return _error("Waitlist entry not found.", 404)

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return _error("Request body must be a JSON object.", 400)

    if "priority" in data:
        if data["priority"] not in WAITLIST_PRIORITIES:
            return _error("priority must be one of: normal, high, urgent.", 422)
        entry.priority = data["priority"]

    if "status" in data:
        if data["status"] not in WAITLIST_STATUSES:
            return _error("status must be one of: waiting, booked, cancelled.", 422)
        entry.status = data["status"]

    if "procedure" in data:
        entry.procedure = str(data["procedure"] or "").strip() or None

    if "preferred_time" in data:
        entry.preferred_time = str(data["preferred_time"] or "").strip() or None

    if "preferred_date" in data:
        if data["preferred_date"]:
            try:
                entry.preferred_date = date.fromisoformat(data["preferred_date"])
            except (ValueError, TypeError):
                return _error("preferred_date must be an ISO date.", 422)
        else:
            entry.preferred_date = None

    if "notes" in data:
        entry.notes = str(data["notes"] or "").strip() or None

    log_activity(
        action="waitlist_updated",
        resource_type="waitlist",
        resource_id=entry.id,
        clinic_id=entry.clinic_id,
        details={"status": entry.status, "priority": entry.priority},
    )
    db.session.commit()

    return jsonify({"data": _serialize_waitlist(entry)})


@waitlist_blueprint.delete("/<int:entry_id>")
@login_required
@require_permission("appointments.delete")
def delete_waitlist_entry(entry_id):
    entry = _scoped_waitlist(entry_id)
    if not entry:
        return _error("Waitlist entry not found.", 404)

    log_activity(
        action="waitlist_deleted",
        resource_type="waitlist",
        resource_id=entry.id,
        clinic_id=entry.clinic_id,
        details={"patient_id": entry.patient_id},
    )
    db.session.delete(entry)
    db.session.commit()

    return jsonify({"message": "Waitlist entry deleted successfully."})


@waitlist_blueprint.post("/<int:entry_id>/auto-fill")
@login_required
@require_permission("appointments.create")
def auto_fill_waitlist_entry(entry_id):
    entry = _scoped_waitlist(entry_id)
    if not entry:
        return _error("Waitlist entry not found.", 404)

    data = request.get_json(silent=True) or {}
    target_date_str = data.get("date") or (entry.preferred_date.isoformat() if entry.preferred_date else None)
    target_time_str = data.get("start_time") or "09:00"

    if not target_date_str:
        return _error("date is required to book this slot.", 400)

    try:
        parsed_date = date.fromisoformat(target_date_str)
        parsed_time = datetime.strptime(target_time_str, "%H:%M").time()
    except (ValueError, TypeError):
        return _error("Invalid date or start_time format.", 422)

    duration = int(data.get("duration") or 30)
    doctor_id = data.get("doctor_id") or entry.doctor_id

    if doctor_id is not None:
        doctor = db.session.scalar(
            db.select(User).where(
                User.id == doctor_id,
                User.clinic_id == g.current_user.clinic_id,
            )
        )
        if not doctor:
            return _error("Doctor not found.", 404)

    # Create the appointment
    appointment = Appointment(
        clinic_id=entry.clinic_id,
        patient_id=entry.patient_id,
        doctor_id=doctor_id,
        date=parsed_date,
        start_time=parsed_time,
        duration=duration,
        status="booked",
        procedure=entry.procedure or "Waitlist Booking",
        notes=f"Auto-filled from wait-list (Priority: {entry.priority}). {entry.notes or ''}".strip(),
        created_by=g.current_user.id,
    )
    db.session.add(appointment)

    # Mark waitlist as booked
    entry.status = "booked"

    log_activity(
        action="waitlist_auto_filled",
        resource_type="appointment",
        resource_id=entry.id,
        clinic_id=entry.clinic_id,
        details={
            "patient_id": entry.patient_id,
            "date": target_date_str,
            "start_time": target_time_str,
            "waitlist_id": entry.id,
        },
    )
    db.session.commit()

    return jsonify({
        "data": {
            "appointment": {
                "id": appointment.id,
                "patient_id": appointment.patient_id,
                "date": appointment.date.isoformat(),
                "start_time": appointment.start_time.strftime("%H:%M"),
                "duration": appointment.duration,
                "status": appointment.status,
                "procedure": appointment.procedure,
                "notes": appointment.notes,
            },
            "waitlist": _serialize_waitlist(entry),
        }
    }), 201
