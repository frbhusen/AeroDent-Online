from datetime import datetime, timedelta, timezone
import re
from flask import Blueprint, g, jsonify, request
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from backend.auth.routes import get_current_user
from backend.auth.service import hash_password
from backend.extensions import db
from backend.models import Clinic, User
from backend.services.audit import log_activity


admin_blueprint = Blueprint("admin", __name__, url_prefix="/api/admin")

EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
VALID_ADMIN_ROLES = frozenset({"super_admin", "head_doctor", "doctor", "secretary"})
VALID_SUBSCRIPTION_STATUSES = frozenset({"active", "trial", "past_due", "suspended", "cancelled"})


def _error(message, status):
    return jsonify({"error": message}), status


@admin_blueprint.before_request
def require_super_admin():
    user = get_current_user()
    if user is None:
        return jsonify({"error": "Authentication required."}), 401
    if user.role != "super_admin":
        return jsonify({"error": "Super Admin access required. You do not have permission."}), 403
    g.current_user = user


def _serialize_clinic(clinic):
    now = datetime.now(timezone.utc)
    head_doctors = [
        {
            "id": u.id,
            "name": u.name,
            "email": u.email,
            "is_active": u.is_active,
        }
        for u in clinic.users
        if u.role == "head_doctor"
    ]
    has_active_head = any(h["is_active"] for h in head_doctors)
    has_inactive_head = any(not h["is_active"] for h in head_doctors)

    is_expired = (
        clinic.subscription_expires_at is not None
        and clinic.subscription_expires_at < now
    )

    doctors_count = sum(1 for u in clinic.users if u.role == "doctor")
    secretaries_count = sum(1 for u in clinic.users if u.role == "secretary")

    # Determine effective status
    if not clinic.is_active:
        effective_status = "clinic_inactive"
    elif clinic.subscription_status in {"suspended", "cancelled"}:
        effective_status = f"subscription_{clinic.subscription_status}"
    elif is_expired:
        effective_status = "subscription_expired"
    elif has_inactive_head and not has_active_head:
        effective_status = "head_doctor_inactive"
    else:
        effective_status = "active"

    return {
        "id": clinic.id,
        "name": clinic.name,
        "phone": clinic.phone,
        "address": clinic.address,
        "currency": clinic.currency,
        "work_start": clinic.work_start.strftime("%H:%M") if clinic.work_start else "09:00",
        "work_end": clinic.work_end.strftime("%H:%M") if clinic.work_end else "18:00",
        "slot_duration": clinic.slot_duration,
        "is_active": clinic.is_active,
        "subscription_status": clinic.subscription_status,
        "subscription_expires_at": (
            clinic.subscription_expires_at.isoformat()
            if clinic.subscription_expires_at
            else None
        ),
        "is_subscription_expired": is_expired,
        "effective_status": effective_status,
        "has_active_head_doctor": has_active_head,
        "head_doctors": head_doctors,
        "staff_summary": {
            "head_doctors": len(head_doctors),
            "doctors": doctors_count,
            "secretaries": secretaries_count,
            "total_users": len(clinic.users),
        },
        "created_at": clinic.created_at.isoformat() if clinic.created_at else None,
    }


def _serialize_user_admin(user):
    return {
        "id": user.id,
        "clinic_id": user.clinic_id,
        "clinic_name": user.clinic.name if user.clinic else "Platform Administration",
        "name": user.name,
        "email": user.email,
        "role": user.role,
        "is_active": user.is_active,
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }


# ==========================================
# Platform Metrics
# ==========================================
@admin_blueprint.get("/metrics")
def get_metrics():
    now = datetime.now(timezone.utc)

    total_clinics = db.session.scalar(db.select(func.count(Clinic.id))) or 0
    active_clinics = db.session.scalar(
        db.select(func.count(Clinic.id)).where(Clinic.is_active.is_(True))
    ) or 0
    inactive_clinics = total_clinics - active_clinics

    active_subscriptions = db.session.scalar(
        db.select(func.count(Clinic.id)).where(
            Clinic.is_active.is_(True),
            Clinic.subscription_status.in_(["active", "trial"]),
            db.or_(
                Clinic.subscription_expires_at.is_(None),
                Clinic.subscription_expires_at >= now,
            ),
        )
    ) or 0

    expired_subscriptions = db.session.scalar(
        db.select(func.count(Clinic.id)).where(
            Clinic.subscription_expires_at.is_not(None),
            Clinic.subscription_expires_at < now,
        )
    ) or 0

    suspended_clinics = db.session.scalar(
        db.select(func.count(Clinic.id)).where(
            Clinic.subscription_status.in_(["suspended", "cancelled"])
        )
    ) or 0

    total_users = db.session.scalar(
        db.select(func.count(User.id)).where(User.role != "super_admin")
    ) or 0
    head_doctors = db.session.scalar(
        db.select(func.count(User.id)).where(User.role == "head_doctor")
    ) or 0
    doctors = db.session.scalar(
        db.select(func.count(User.id)).where(User.role == "doctor")
    ) or 0
    secretaries = db.session.scalar(
        db.select(func.count(User.id)).where(User.role == "secretary")
    ) or 0
    active_users = db.session.scalar(
        db.select(func.count(User.id)).where(
            User.role != "super_admin",
            User.is_active.is_(True),
        )
    ) or 0

    return jsonify(
        {
            "data": {
                "total_clinics": total_clinics,
                "active_clinics": active_clinics,
                "inactive_clinics": inactive_clinics,
                "active_subscriptions": active_subscriptions,
                "expired_subscriptions": expired_subscriptions,
                "suspended_clinics": suspended_clinics,
                "total_users": total_users,
                "total_head_doctors": head_doctors,
                "total_doctors": doctors,
                "total_secretaries": secretaries,
                "active_users": active_users,
                "inactive_users": total_users - active_users,
            }
        }
    )


# ==========================================
# Clinics Management
# ==========================================
@admin_blueprint.get("/clinics")
def list_clinics():
    search = request.args.get("search", "").strip()
    status_filter = request.args.get("status", "all").strip().lower()

    query = db.select(Clinic).order_by(Clinic.id.desc())

    if search:
        search_pattern = f"%{search}%"
        query = query.where(
            db.or_(
                Clinic.name.ilike(search_pattern),
                Clinic.phone.ilike(search_pattern),
            )
        )

    clinics = db.session.scalars(query).all()
    serialized = [_serialize_clinic(c) for c in clinics]

    if status_filter != "all":
        if status_filter == "active":
            serialized = [c for c in serialized if c["effective_status"] == "active"]
        elif status_filter == "inactive":
            serialized = [c for c in serialized if c["effective_status"] != "active"]
        elif status_filter == "expired":
            serialized = [c for c in serialized if c["is_subscription_expired"]]
        elif status_filter == "suspended":
            serialized = [c for c in serialized if "suspended" in c["effective_status"] or "cancelled" in c["effective_status"]]
        elif status_filter == "head_doctor_inactive":
            serialized = [c for c in serialized if c["effective_status"] == "head_doctor_inactive"]

    return jsonify({"data": serialized})


@admin_blueprint.get("/clinics/<int:clinic_id>")
def get_clinic(clinic_id):
    clinic = db.session.get(Clinic, clinic_id)
    if clinic is None:
        return _error("Clinic not found.", 404)

    return jsonify({"data": _serialize_clinic(clinic)})


@admin_blueprint.post("/clinics")
def create_clinic():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return _error("Request body must be a JSON object.", 400)

    clinic_name = data.get("name")
    phone = data.get("phone", "")
    address = data.get("address", "")
    currency = data.get("currency", "SYR")
    subscription_status = data.get("subscription_status", "active")
    subscription_expires_at_raw = data.get("subscription_expires_at")
    is_active = data.get("is_active", True)

    head_name = data.get("head_doctor_name")
    head_email = data.get("head_doctor_email")
    head_password = data.get("head_doctor_password")

    if not isinstance(clinic_name, str) or not clinic_name.strip():
        return _error("Clinic name is required.", 422)
    if not isinstance(head_name, str) or not head_name.strip():
        return _error("Head doctor name is required.", 422)
    if not isinstance(head_email, str) or not EMAIL_REGEX.match(head_email.strip()):
        return _error("A valid head doctor email is required.", 422)
    if not isinstance(head_password, str) or len(head_password) < 8:
        return _error("Head doctor password must be at least 8 characters.", 422)

    if subscription_status not in VALID_SUBSCRIPTION_STATUSES:
        return _error(f"Invalid subscription status. Must be one of {sorted(VALID_SUBSCRIPTION_STATUSES)}", 400)

    head_email = head_email.strip().lower()
    existing_user = db.session.scalar(
        db.select(User.id).where(func.lower(User.email) == head_email)
    )
    if existing_user is not None:
        return _error("A user with this email already exists.", 409)

    subscription_expires_at = None
    if subscription_expires_at_raw:
        try:
            subscription_expires_at = datetime.fromisoformat(subscription_expires_at_raw.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return _error("Invalid subscription_expires_at ISO datetime.", 422)

    clinic = Clinic(
        name=clinic_name.strip(),
        phone=phone.strip() if isinstance(phone, str) else None,
        address=address.strip() if isinstance(address, str) else None,
        currency=currency.strip().upper() if isinstance(currency, str) else "SYR",
        subscription_status=subscription_status,
        subscription_expires_at=subscription_expires_at,
        is_active=bool(is_active),
    )
    db.session.add(clinic)
    db.session.flush()

    head_doctor = User(
        clinic_id=clinic.id,
        name=head_name.strip(),
        email=head_email,
        password_hash=hash_password(head_password),
        role="head_doctor",
        is_active=True,
    )
    db.session.add(head_doctor)

    try:
        log_activity(
            action="admin_clinic_created",
            resource_type="clinic",
            resource_id=clinic.id,
            clinic_id=clinic.id,
            details={"name": clinic.name, "head_doctor_email": head_email},
        )
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return _error("Clinic could not be created.", 409)

    return jsonify({"data": _serialize_clinic(clinic)}), 201


@admin_blueprint.patch("/clinics/<int:clinic_id>")
def update_clinic(clinic_id):
    clinic = db.session.get(Clinic, clinic_id)
    if clinic is None:
        return _error("Clinic not found.", 404)

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return _error("Request body must be a JSON object.", 400)

    if not data:
        return _error("At least one field is required to update.", 400)

    allowed_fields = {
        "name",
        "phone",
        "address",
        "currency",
        "is_active",
        "subscription_status",
        "subscription_expires_at",
        "extend_days",
    }
    unsupported = set(data) - allowed_fields
    if unsupported:
        return _error(f"Unsupported fields: {sorted(unsupported)}", 400)

    if "name" in data:
        if not isinstance(data["name"], str) or not data["name"].strip():
            return _error("Clinic name cannot be blank.", 422)
        clinic.name = data["name"].strip()

    if "phone" in data:
        clinic.phone = data["phone"].strip() if isinstance(data["phone"], str) else None

    if "address" in data:
        clinic.address = data["address"].strip() if isinstance(data["address"], str) else None

    if "currency" in data:
        clinic.currency = str(data["currency"]).strip().upper()

    if "is_active" in data:
        if not isinstance(data["is_active"], bool):
            return _error("is_active must be a boolean.", 422)
        clinic.is_active = data["is_active"]

    if "subscription_status" in data:
        status = str(data["subscription_status"]).strip().lower()
        if status not in VALID_SUBSCRIPTION_STATUSES:
            return _error(f"Invalid subscription status. Must be one of {sorted(VALID_SUBSCRIPTION_STATUSES)}", 400)
        clinic.subscription_status = status

    if "subscription_expires_at" in data:
        raw_val = data["subscription_expires_at"]
        if raw_val is None or raw_val == "":
            clinic.subscription_expires_at = None
        else:
            try:
                clinic.subscription_expires_at = datetime.fromisoformat(str(raw_val).replace("Z", "+00:00"))
            except (ValueError, TypeError):
                return _error("Invalid subscription_expires_at ISO datetime.", 422)

    if "extend_days" in data:
        try:
            days = int(data["extend_days"])
            if days <= 0:
                return _error("extend_days must be a positive integer.", 422)
            base_date = clinic.subscription_expires_at or datetime.now(timezone.utc)
            if base_date < datetime.now(timezone.utc):
                base_date = datetime.now(timezone.utc)
            clinic.subscription_expires_at = base_date + timedelta(days=days)
            clinic.subscription_status = "active"
            clinic.is_active = True
        except (ValueError, TypeError):
            return _error("extend_days must be an integer.", 422)

    try:
        log_activity(
            action="admin_clinic_updated",
            resource_type="clinic",
            resource_id=clinic.id,
            clinic_id=clinic.id,
            details=data,
        )
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return _error("Clinic could not be updated.", 409)

    return jsonify({"data": _serialize_clinic(clinic)})


def purge_clinic_data(clinic_id):
    """
    Completely and cleanly purges all data related to a clinic in foreign key safe order.
    """
    from backend.models import (
        Appointment,
        AuditLog,
        InventoryBatch,
        InventoryCategory,
        InventoryItem,
        InventoryMovement,
        InventorySupplier,
        Invoice,
        Odontogram,
        Patient,
        Payment,
        Prescription,
        PrescriptionMedication,
        Treatment,
        TreatmentPlan,
        User,
        XRay,
    )

    # 0. Payments & Audit Logs
    db.session.query(Payment).filter(Payment.clinic_id == clinic_id).delete(synchronize_session=False)
    db.session.query(AuditLog).filter(AuditLog.clinic_id == clinic_id).delete(synchronize_session=False)

    # 1. Invoices
    db.session.query(Invoice).filter(Invoice.clinic_id == clinic_id).delete(synchronize_session=False)

    # 2. X-rays
    db.session.query(XRay).filter(XRay.clinic_id == clinic_id).delete(synchronize_session=False)

    # 3. Prescriptions & Medications
    prescription_ids = db.session.scalars(
        db.select(Prescription.id).where(Prescription.clinic_id == clinic_id)
    ).all()
    if prescription_ids:
        db.session.query(PrescriptionMedication).filter(
            PrescriptionMedication.prescription_id.in_(prescription_ids)
        ).delete(synchronize_session=False)
    db.session.query(Prescription).filter(Prescription.clinic_id == clinic_id).delete(synchronize_session=False)

    # 4. Appointments
    db.session.query(Appointment).filter(Appointment.clinic_id == clinic_id).delete(synchronize_session=False)

    # 5. Treatment Plans
    db.session.query(TreatmentPlan).filter(TreatmentPlan.clinic_id == clinic_id).delete(synchronize_session=False)

    # 6. Treatments
    db.session.query(Treatment).filter(Treatment.clinic_id == clinic_id).delete(synchronize_session=False)

    # 7. Odontograms
    db.session.query(Odontogram).filter(Odontogram.clinic_id == clinic_id).delete(synchronize_session=False)

    # 8. Patients
    db.session.query(Patient).filter(Patient.clinic_id == clinic_id).delete(synchronize_session=False)

    # 9a. Inventory (movements reference staff, so they must go before users)
    for model in (InventoryMovement, InventoryBatch, InventoryItem, InventoryCategory, InventorySupplier):
        db.session.query(model).filter(model.clinic_id == clinic_id).delete(synchronize_session=False)

    # 9. Clinic Staff (all users under this clinic)
    db.session.query(User).filter(User.clinic_id == clinic_id).delete(synchronize_session=False)

    # 10. The Clinic itself
    clinic = db.session.get(Clinic, clinic_id)
    if clinic:
        db.session.delete(clinic)


@admin_blueprint.delete("/clinics/<int:clinic_id>")
def delete_clinic(clinic_id):
    clinic = db.session.get(Clinic, clinic_id)
    if clinic is None:
        return _error("Clinic not found.", 404)

    clinic_name = clinic.name

    try:
        purge_clinic_data(clinic_id)
        # clinic_id=None (platform-level record): purge_clinic_data already deleted this
        # clinic's own audit logs and the clinic row itself cascades that deletion, so a
        # clinic-scoped entry here would vanish immediately. Force clinic_id back to None
        # after the call since log_activity falls back to g.current_clinic/g.current_user's
        # clinic when given clinic_id=None, and g.current_clinic may still hold a stale value
        # from an unrelated earlier request in a long-lived app/request context.
        entry = log_activity(
            action="admin_clinic_deleted",
            resource_type="clinic",
            resource_id=clinic_id,
            clinic_id=None,
            details={"name": clinic_name},
        )
        if entry is not None:
            entry.clinic_id = None
        db.session.commit()
        return "", 204
    except Exception as e:
        db.session.rollback()
        return _error(f"Failed to delete clinic: {str(e)}", 500)


# ==========================================
# Global Users Management
# ==========================================
@admin_blueprint.get("/users")
def list_users():
    clinic_id = request.args.get("clinic_id", type=int)
    role = request.args.get("role")
    search = request.args.get("search", "").strip()
    is_active_raw = request.args.get("is_active")

    query = db.select(User).order_by(User.id.desc())

    if clinic_id is not None:
        query = query.where(User.clinic_id == clinic_id)
    if role and role in VALID_ADMIN_ROLES:
        query = query.where(User.role == role)
    if is_active_raw is not None:
        is_active_val = is_active_raw.lower() in ("true", "1")
        query = query.where(User.is_active == is_active_val)
    if search:
        search_pattern = f"%{search}%"
        query = query.where(
            db.or_(
                User.name.ilike(search_pattern),
                User.email.ilike(search_pattern),
            )
        )

    users = db.session.scalars(query).all()
    return jsonify({"data": [_serialize_user_admin(u) for u in users]})


@admin_blueprint.post("/users")
def create_user():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return _error("Request body must be a JSON object.", 400)

    clinic_id = data.get("clinic_id")
    name = data.get("name")
    email = data.get("email")
    password = data.get("password")
    role = data.get("role")
    is_active = data.get("is_active", True)

    if not isinstance(name, str) or not name.strip():
        return _error("Name is required.", 422)
    if not isinstance(email, str) or not EMAIL_REGEX.match(email.strip()):
        return _error("Valid email is required.", 422)
    if not isinstance(password, str) or len(password) < 8:
        return _error("Password must be at least 8 characters.", 422)
    if role not in VALID_ADMIN_ROLES:
        return _error("Invalid role.", 400)

    if role != "super_admin":
        if clinic_id is None:
            return _error("clinic_id is required for non-super-admin users.", 422)
        clinic = db.session.get(Clinic, clinic_id)
        if clinic is None:
            return _error("Specified clinic does not exist.", 404)
    else:
        clinic_id = None

    email = email.strip().lower()
    existing_user = db.session.scalar(
        db.select(User.id).where(func.lower(User.email) == email)
    )
    if existing_user is not None:
        return _error("A user with this email already exists.", 409)

    user = User(
        clinic_id=clinic_id,
        name=name.strip(),
        email=email,
        password_hash=hash_password(password),
        role=role,
        is_active=bool(is_active),
    )
    db.session.add(user)
    try:
        db.session.flush()
        log_activity(
            action="admin_user_created",
            resource_type="user",
            resource_id=user.id,
            clinic_id=user.clinic_id,
            details={"email": user.email, "role": user.role},
        )
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return _error("User could not be created.", 409)

    return jsonify({"data": _serialize_user_admin(user)}), 201


@admin_blueprint.patch("/users/<int:user_id>")
def update_user(user_id):
    user = db.session.get(User, user_id)
    if user is None:
        return _error("User not found.", 404)

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return _error("Request body must be a JSON object.", 400)

    if not data:
        return _error("At least one field is required to update.", 400)

    allowed_fields = {"name", "email", "role", "is_active", "password", "clinic_id"}
    unsupported = set(data) - allowed_fields
    if unsupported:
        return _error(f"Unsupported fields: {sorted(unsupported)}", 400)

    if "name" in data:
        if not isinstance(data["name"], str) or not data["name"].strip():
            return _error("Name cannot be blank.", 422)
        user.name = data["name"].strip()

    if "email" in data:
        if not isinstance(data["email"], str) or not EMAIL_REGEX.match(data["email"].strip()):
            return _error("A valid email address is required.", 422)
        new_email = data["email"].strip().lower()
        if new_email != user.email:
            existing = db.session.scalar(
                db.select(User.id).where(
                    func.lower(User.email) == new_email,
                    User.id != user.id,
                )
            )
            if existing is not None:
                return _error("A user with this email already exists.", 409)
            user.email = new_email

    if "role" in data:
        new_role = data["role"]
        if new_role not in VALID_ADMIN_ROLES:
            return _error("Invalid role.", 400)
        # Prevent demoting the last super admin
        if user.role == "super_admin" and new_role != "super_admin":
            super_count = db.session.scalar(
                db.select(func.count(User.id)).where(
                    User.role == "super_admin",
                    User.is_active.is_(True),
                    User.id != user.id,
                )
            )
            if super_count == 0:
                return _error("Cannot demote the only active Super Admin.", 422)
        user.role = new_role

    if "is_active" in data:
        new_status = data["is_active"]
        if not isinstance(new_status, bool):
            return _error("is_active must be a boolean.", 422)
        if user.role == "super_admin" and not new_status:
            super_count = db.session.scalar(
                db.select(func.count(User.id)).where(
                    User.role == "super_admin",
                    User.is_active.is_(True),
                    User.id != user.id,
                )
            )
            if super_count == 0:
                return _error("Cannot deactivate the only active Super Admin.", 422)
        user.is_active = new_status

    if "password" in data:
        pwd = data["password"]
        if not isinstance(pwd, str) or len(pwd) < 8:
            return _error("Password must be at least 8 characters.", 422)
        user.password_hash = hash_password(pwd)

    if "clinic_id" in data:
        new_cid = data["clinic_id"]
        if new_cid is not None:
            c = db.session.get(Clinic, new_cid)
            if c is None:
                return _error("Clinic not found.", 404)
        user.clinic_id = new_cid

    try:
        log_activity(
            action="admin_user_updated",
            resource_type="user",
            resource_id=user.id,
            clinic_id=user.clinic_id,
            details={k: v for k, v in data.items() if k != "password"},
        )
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return _error("User could not be updated.", 409)

    return jsonify({"data": _serialize_user_admin(user)})


@admin_blueprint.delete("/users/<int:user_id>")
def delete_user(user_id):
    user = db.session.get(User, user_id)
    if user is None:
        return _error("User not found.", 404)

    if user.id == g.current_user.id:
        return _error("You cannot delete your own account.", 400)

    if user.role == "super_admin":
        super_count = db.session.scalar(
            db.select(func.count(User.id)).where(
                User.role == "super_admin",
                User.is_active.is_(True),
                User.id != user.id,
            )
        )
        if super_count == 0:
            return _error("Cannot delete the only active Super Admin.", 422)

    deleted_email = user.email
    deleted_role = user.role
    deleted_clinic_id = user.clinic_id

    db.session.delete(user)
    try:
        log_activity(
            action="admin_user_deleted",
            resource_type="user",
            resource_id=user_id,
            clinic_id=deleted_clinic_id,
            details={"email": deleted_email, "role": deleted_role},
        )
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return _error(
            "User has associated records and cannot be permanently deleted. Deactivate the account instead.",
            409,
        )

    return "", 204
