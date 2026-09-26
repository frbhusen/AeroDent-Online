from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from flask import Blueprint, g, jsonify, request
from sqlalchemy import func

from backend.auth import login_required, require_permission
from backend.extensions import db
from backend.models import StaffCredential, StaffShift, TimeClock, User
from backend.services.audit import log_activity


hr_blueprint = Blueprint("hr", __name__, url_prefix="/api/hr")

VALID_SHIFT_STATUSES = frozenset({"scheduled", "completed", "absent", "leave"})
VALID_CREDENTIAL_TYPES = frozenset({"license", "certification", "insurance", "registration", "other"})
VALID_CREDENTIAL_STATUSES = frozenset({"active", "expired", "revoked"})


def _error(message, status):
    return jsonify({"error": message}), status


def _scoped_shift(shift_id):
    return db.session.scalar(
        db.select(StaffShift).where(
            StaffShift.id == shift_id,
            StaffShift.clinic_id == g.current_user.clinic_id,
        )
    )


def _scoped_credential(credential_id):
    return db.session.scalar(
        db.select(StaffCredential).where(
            StaffCredential.id == credential_id,
            StaffCredential.clinic_id == g.current_user.clinic_id,
        )
    )


def _serialize_shift(item):
    return {
        "id": item.id,
        "clinic_id": item.clinic_id,
        "user_id": item.user_id,
        "user_name": item.user.name if item.user else f"Staff #{item.user_id}",
        "user_role": item.user.role if item.user else "",
        "date": item.date.isoformat(),
        "start_time": item.start_time.strftime("%H:%M"),
        "end_time": item.end_time.strftime("%H:%M"),
        "shift_type": item.shift_type,
        "status": item.status,
        "notes": item.notes or "",
        "created_by": item.created_by,
        "created_at": item.created_at.isoformat() if item.created_at else None,
    }


def _serialize_time_clock(item):
    return {
        "id": item.id,
        "clinic_id": item.clinic_id,
        "user_id": item.user_id,
        "user_name": item.user.name if item.user else f"Staff #{item.user_id}",
        "user_role": item.user.role if item.user else "",
        "clock_in": item.clock_in.isoformat(),
        "clock_out": item.clock_out.isoformat() if item.clock_out else None,
        "total_hours": float(item.total_hours) if item.total_hours is not None else None,
        "status": item.status,
        "notes": item.notes or "",
        "created_at": item.created_at.isoformat() if item.created_at else None,
    }


def _serialize_credential(item):
    today = date.today()
    days_remaining = (item.expiry_date - today).days
    if days_remaining < 0:
        computed_status = "expired"
    elif days_remaining <= 30:
        computed_status = "expiring_soon"
    else:
        computed_status = item.status

    return {
        "id": item.id,
        "clinic_id": item.clinic_id,
        "user_id": item.user_id,
        "user_name": item.user.name if item.user else f"Staff #{item.user_id}",
        "user_role": item.user.role if item.user else "",
        "title": item.title,
        "credential_type": item.credential_type,
        "credential_number": item.credential_number or "",
        "issuing_authority": item.issuing_authority or "",
        "issue_date": item.issue_date.isoformat() if item.issue_date else None,
        "expiry_date": item.expiry_date.isoformat(),
        "status": item.status,
        "computed_status": computed_status,
        "days_remaining": days_remaining,
        "notes": item.notes or "",
        "created_by": item.created_by,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
    }


# ==========================================
# 1. Staff Scheduling (Shifts)
# ==========================================

@hr_blueprint.get("/shifts")
@login_required
def list_shifts():
    query = (
        db.select(StaffShift)
        .where(StaffShift.clinic_id == g.current_user.clinic_id)
        .join(StaffShift.user)
    )

    if "user_id" in request.args:
        try:
            query = query.where(StaffShift.user_id == int(request.args["user_id"]))
        except ValueError:
            return _error("user_id must be an integer.", 400)
    elif g.current_user.role not in {"head_doctor", "super_admin"} and request.args.get("my_only") == "true":
        query = query.where(StaffShift.user_id == g.current_user.id)

    if "start_date" in request.args:
        try:
            query = query.where(StaffShift.date >= date.fromisoformat(request.args["start_date"]))
        except ValueError:
            return _error("start_date must be an ISO date.", 422)

    if "end_date" in request.args:
        try:
            query = query.where(StaffShift.date <= date.fromisoformat(request.args["end_date"]))
        except ValueError:
            return _error("end_date must be an ISO date.", 422)

    if "status" in request.args and request.args["status"] != "all":
        query = query.where(StaffShift.status == request.args["status"])

    records = db.session.scalars(query.order_by(StaffShift.date.asc(), StaffShift.start_time.asc())).all()
    return jsonify({"data": [_serialize_shift(s) for s in records], "meta": {"count": len(records)}})


@hr_blueprint.post("/shifts")
@login_required
def create_shift():
    if g.current_user.role not in {"head_doctor", "super_admin"}:
        return _error("Only head doctors or administrators can create staff shifts.", 403)

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return _error("Request body must be a JSON object.", 400)

    user_id = data.get("user_id")
    if not isinstance(user_id, int):
        return _error("user_id is required and must be an integer.", 400)

    target_user = db.session.scalar(
        db.select(User).where(
            User.id == user_id,
            User.clinic_id == g.current_user.clinic_id,
        )
    )
    if not target_user:
        return _error("Staff member not found.", 404)

    try:
        shift_date = date.fromisoformat(data.get("date", ""))
        start_time = datetime.strptime(data.get("start_time", ""), "%H:%M").time()
        end_time = datetime.strptime(data.get("end_time", ""), "%H:%M").time()
    except (ValueError, TypeError):
        return _error("Invalid date or time format. Use YYYY-MM-DD and HH:MM.", 422)

    if start_time >= end_time:
        return _error("start_time must be earlier than end_time.", 422)

    status = data.get("status", "scheduled")
    if status not in VALID_SHIFT_STATUSES:
        return _error("Invalid shift status.", 422)

    shift = StaffShift(
        clinic_id=g.current_user.clinic_id,
        user_id=user_id,
        date=shift_date,
        start_time=start_time,
        end_time=end_time,
        shift_type=str(data.get("shift_type") or "regular").strip(),
        status=status,
        notes=str(data.get("notes") or "").strip() or None,
        created_by=g.current_user.id,
    )
    db.session.add(shift)
    db.session.flush()

    log_activity(
        action="shift_created",
        resource_type="staff_shift",
        resource_id=shift.id,
        clinic_id=shift.clinic_id,
        details={"user_id": shift.user_id, "date": str(shift.date), "shift_type": shift.shift_type},
    )
    db.session.commit()

    return jsonify({"data": _serialize_shift(shift)}), 201


@hr_blueprint.patch("/shifts/<int:shift_id>")
@login_required
def update_shift(shift_id):
    if g.current_user.role not in {"head_doctor", "super_admin"}:
        return _error("Only head doctors or administrators can update staff shifts.", 403)

    shift = _scoped_shift(shift_id)
    if not shift:
        return _error("Shift not found.", 404)

    data = request.get_json(silent=True) or {}
    if "date" in data:
        try:
            shift.date = date.fromisoformat(data["date"])
        except ValueError:
            return _error("date must be an ISO date.", 422)

    if "start_time" in data:
        try:
            shift.start_time = datetime.strptime(data["start_time"], "%H:%M").time()
        except ValueError:
            return _error("start_time must be HH:MM.", 422)

    if "end_time" in data:
        try:
            shift.end_time = datetime.strptime(data["end_time"], "%H:%M").time()
        except ValueError:
            return _error("end_time must be HH:MM.", 422)

    if "shift_type" in data:
        shift.shift_type = str(data["shift_type"] or "regular").strip()

    if "status" in data:
        if data["status"] not in VALID_SHIFT_STATUSES:
            return _error("Invalid shift status.", 422)
        shift.status = data["status"]

    if "notes" in data:
        shift.notes = str(data["notes"] or "").strip() or None

    log_activity(
        action="shift_updated",
        resource_type="staff_shift",
        resource_id=shift.id,
        clinic_id=shift.clinic_id,
        details={"status": shift.status, "date": str(shift.date)},
    )
    db.session.commit()

    return jsonify({"data": _serialize_shift(shift)})


@hr_blueprint.delete("/shifts/<int:shift_id>")
@login_required
def delete_shift(shift_id):
    if g.current_user.role not in {"head_doctor", "super_admin"}:
        return _error("Only head doctors or administrators can delete staff shifts.", 403)

    shift = _scoped_shift(shift_id)
    if not shift:
        return _error("Shift not found.", 404)

    log_activity(
        action="shift_deleted",
        resource_type="staff_shift",
        resource_id=shift.id,
        clinic_id=shift.clinic_id,
        details={"user_id": shift.user_id, "date": str(shift.date)},
    )
    db.session.delete(shift)
    db.session.commit()

    return jsonify({"message": "Shift deleted successfully."})


# ==========================================
# 2. Time Clock (Punch In / Out Attendance)
# ==========================================

@hr_blueprint.get("/time-clock/status")
@login_required
def time_clock_status():
    active_entry = db.session.scalar(
        db.select(TimeClock)
        .where(
            TimeClock.clinic_id == g.current_user.clinic_id,
            TimeClock.user_id == g.current_user.id,
            TimeClock.status == "clocked_in",
        )
        .order_by(TimeClock.id.desc())
    )

    if active_entry:
        now = datetime.now(timezone.utc)
        elapsed_seconds = int((now - active_entry.clock_in).total_seconds())
        return jsonify({
            "clocked_in": True,
            "entry": _serialize_time_clock(active_entry),
            "elapsed_seconds": max(0, elapsed_seconds),
        })

    return jsonify({
        "clocked_in": False,
        "entry": None,
        "elapsed_seconds": 0,
    })


@hr_blueprint.post("/time-clock/punch")
@login_required
def time_clock_punch():
    now = datetime.now(timezone.utc)
    active_entry = db.session.scalar(
        db.select(TimeClock)
        .where(
            TimeClock.clinic_id == g.current_user.clinic_id,
            TimeClock.user_id == g.current_user.id,
            TimeClock.status == "clocked_in",
        )
        .order_by(TimeClock.id.desc())
    )

    data = request.get_json(silent=True) or {}
    notes = str(data.get("notes") or "").strip() or None

    if active_entry:
        # Clock out
        active_entry.clock_out = now
        active_entry.status = "clocked_out"
        total_seconds = (now - active_entry.clock_in).total_seconds()
        active_entry.total_hours = Decimal(str(round(total_seconds / 3600.0, 2)))
        if notes:
            active_entry.notes = f"{active_entry.notes or ''} | {notes}".strip(" |")

        log_activity(
            action="time_clock_out",
            resource_type="time_clock",
            resource_id=active_entry.id,
            clinic_id=active_entry.clinic_id,
            details={"hours": float(active_entry.total_hours)},
        )
        db.session.commit()

        return jsonify({
            "action": "clock_out",
            "message": f"Successfully clocked out. Total time: {active_entry.total_hours} hrs.",
            "data": _serialize_time_clock(active_entry),
        })
    else:
        # Clock in
        entry = TimeClock(
            clinic_id=g.current_user.clinic_id,
            user_id=g.current_user.id,
            clock_in=now,
            status="clocked_in",
            notes=notes,
            ip_address=request.remote_addr,
        )
        db.session.add(entry)
        db.session.flush()

        log_activity(
            action="time_clock_in",
            resource_type="time_clock",
            resource_id=entry.id,
            clinic_id=entry.clinic_id,
            details={"clock_in": entry.clock_in.isoformat()},
        )
        db.session.commit()

        return jsonify({
            "action": "clock_in",
            "message": "Successfully clocked in.",
            "data": _serialize_time_clock(entry),
        }), 201


@hr_blueprint.get("/time-clock/records")
@login_required
def list_time_clock_records():
    query = (
        db.select(TimeClock)
        .where(TimeClock.clinic_id == g.current_user.clinic_id)
        .join(TimeClock.user)
    )

    if g.current_user.role not in {"head_doctor", "super_admin"}:
        query = query.where(TimeClock.user_id == g.current_user.id)
    elif "user_id" in request.args:
        try:
            query = query.where(TimeClock.user_id == int(request.args["user_id"]))
        except ValueError:
            return _error("user_id must be an integer.", 400)

    if "start_date" in request.args:
        try:
            d = date.fromisoformat(request.args["start_date"])
            query = query.where(func.date(TimeClock.clock_in) >= d)
        except ValueError:
            return _error("start_date must be an ISO date.", 422)

    if "end_date" in request.args:
        try:
            d = date.fromisoformat(request.args["end_date"])
            query = query.where(func.date(TimeClock.clock_in) <= d)
        except ValueError:
            return _error("end_date must be an ISO date.", 422)

    records = db.session.scalars(query.order_by(TimeClock.clock_in.desc()).limit(150)).all()
    return jsonify({"data": [_serialize_time_clock(r) for r in records], "meta": {"count": len(records)}})


# ==========================================
# 3. Staff Credentials & License Expirations
# ==========================================

@hr_blueprint.get("/credentials")
@login_required
def list_credentials():
    query = (
        db.select(StaffCredential)
        .where(StaffCredential.clinic_id == g.current_user.clinic_id)
        .join(StaffCredential.user)
    )

    if g.current_user.role not in {"head_doctor", "super_admin"}:
        query = query.where(StaffCredential.user_id == g.current_user.id)
    elif "user_id" in request.args:
        try:
            query = query.where(StaffCredential.user_id == int(request.args["user_id"]))
        except ValueError:
            return _error("user_id must be an integer.", 400)

    records = db.session.scalars(query.order_by(StaffCredential.expiry_date.asc())).all()
    serialized = [_serialize_credential(c) for c in records]

    # Filter by status / urgency if requested
    filter_status = request.args.get("status")
    if filter_status and filter_status != "all":
        serialized = [c for c in serialized if c["computed_status"] == filter_status or c["status"] == filter_status]

    return jsonify({"data": serialized, "meta": {"count": len(serialized)}})


@hr_blueprint.get("/credentials/summary")
@login_required
def credentials_summary():
    query = (
        db.select(StaffCredential)
        .where(StaffCredential.clinic_id == g.current_user.clinic_id)
    )
    if g.current_user.role not in {"head_doctor", "super_admin"}:
        query = query.where(StaffCredential.user_id == g.current_user.id)

    records = db.session.scalars(query).all()
    today = date.today()
    active_count = 0
    expiring_soon_count = 0
    expired_count = 0

    for item in records:
        days = (item.expiry_date - today).days
        if days < 0:
            expired_count += 1
        elif days <= 30:
            expiring_soon_count += 1
        else:
            active_count += 1

    return jsonify({
        "data": {
            "total": len(records),
            "active": active_count,
            "expiring_soon": expiring_soon_count,
            "expired": expired_count,
            "needs_attention": expiring_soon_count + expired_count,
        }
    })


@hr_blueprint.post("/credentials")
@login_required
def create_credential():
    if g.current_user.role not in {"head_doctor", "super_admin"}:
        return _error("Only head doctors or administrators can register staff credentials.", 403)

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return _error("Request body must be a JSON object.", 400)

    user_id = data.get("user_id")
    if not isinstance(user_id, int):
        return _error("user_id is required and must be an integer.", 400)

    target_user = db.session.scalar(
        db.select(User).where(
            User.id == user_id,
            User.clinic_id == g.current_user.clinic_id,
        )
    )
    if not target_user:
        return _error("Staff member not found.", 404)

    title = str(data.get("title") or "").strip()
    if not title:
        return _error("Credential title is required.", 422)

    try:
        expiry_date = date.fromisoformat(data.get("expiry_date", ""))
    except (ValueError, TypeError):
        return _error("expiry_date is required and must be an ISO date (YYYY-MM-DD).", 422)

    issue_date = None
    if data.get("issue_date"):
        try:
            issue_date = date.fromisoformat(data["issue_date"])
        except ValueError:
            return _error("issue_date must be an ISO date.", 422)

    credential = StaffCredential(
        clinic_id=g.current_user.clinic_id,
        user_id=user_id,
        title=title,
        credential_type=data.get("credential_type", "license"),
        credential_number=str(data.get("credential_number") or "").strip() or None,
        issuing_authority=str(data.get("issuing_authority") or "").strip() or None,
        issue_date=issue_date,
        expiry_date=expiry_date,
        status="active",
        notes=str(data.get("notes") or "").strip() or None,
        created_by=g.current_user.id,
    )
    db.session.add(credential)
    db.session.flush()

    log_activity(
        action="credential_added",
        resource_type="staff_credential",
        resource_id=credential.id,
        clinic_id=credential.clinic_id,
        details={"user_id": credential.user_id, "title": credential.title, "expiry_date": str(credential.expiry_date)},
    )
    db.session.commit()

    return jsonify({"data": _serialize_credential(credential)}), 201


@hr_blueprint.patch("/credentials/<int:credential_id>")
@login_required
def update_credential(credential_id):
    if g.current_user.role not in {"head_doctor", "super_admin"}:
        return _error("Only head doctors or administrators can update staff credentials.", 403)

    credential = _scoped_credential(credential_id)
    if not credential:
        return _error("Credential not found.", 404)

    data = request.get_json(silent=True) or {}
    if "title" in data:
        t = str(data["title"] or "").strip()
        if t:
            credential.title = t

    if "credential_number" in data:
        credential.credential_number = str(data["credential_number"] or "").strip() or None

    if "issuing_authority" in data:
        credential.issuing_authority = str(data["issuing_authority"] or "").strip() or None

    if "expiry_date" in data:
        try:
            credential.expiry_date = date.fromisoformat(data["expiry_date"])
        except ValueError:
            return _error("expiry_date must be an ISO date.", 422)

    if "status" in data:
        if data["status"] not in VALID_CREDENTIAL_STATUSES:
            return _error("Invalid credential status.", 422)
        credential.status = data["status"]

    if "notes" in data:
        credential.notes = str(data["notes"] or "").strip() or None

    log_activity(
        action="credential_updated",
        resource_type="staff_credential",
        resource_id=credential.id,
        clinic_id=credential.clinic_id,
        details={"title": credential.title, "status": credential.status},
    )
    db.session.commit()

    return jsonify({"data": _serialize_credential(credential)})


@hr_blueprint.delete("/credentials/<int:credential_id>")
@login_required
def delete_credential(credential_id):
    if g.current_user.role not in {"head_doctor", "super_admin"}:
        return _error("Only head doctors or administrators can delete staff credentials.", 403)

    credential = _scoped_credential(credential_id)
    if not credential:
        return _error("Credential not found.", 404)

    log_activity(
        action="credential_deleted",
        resource_type="staff_credential",
        resource_id=credential.id,
        clinic_id=credential.clinic_id,
        details={"user_id": credential.user_id, "title": credential.title},
    )
    db.session.delete(credential)
    db.session.commit()

    return jsonify({"message": "Credential deleted successfully."})
