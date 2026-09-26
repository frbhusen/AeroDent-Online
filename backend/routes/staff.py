import re
from flask import Blueprint, g, jsonify, request
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from backend.auth import login_required, require_permission
from backend.auth.service import hash_password
from backend.extensions import db
from backend.models import User
from backend.services.audit import log_activity
from backend.services.auth_security import revoke_user_sessions, validate_new_password


staff_blueprint = Blueprint("staff", __name__, url_prefix="/api")

VALID_STAFF_ROLES = frozenset({"head_doctor", "doctor", "secretary"})
EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _error(message, status):
    return jsonify({"error": message}), status


def _serialize_user(user):
    return {
        "id": user.id,
        "clinic_id": user.clinic_id,
        "name": user.name,
        "email": user.email,
        "role": user.role,
        "is_active": user.is_active,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "updated_at": user.updated_at.isoformat() if user.updated_at else None,
    }


def _scoped_user(user_id):
    return db.session.scalar(
        db.select(User).where(
            User.id == user_id,
            User.clinic_id == g.current_user.clinic_id,
        )
    )


@staff_blueprint.get("/doctors")
@login_required
def list_doctors():
    doctors = db.session.scalars(
        db.select(User).where(
            User.clinic_id == g.current_user.clinic_id,
            User.role.in_(["head_doctor", "doctor"]),
            User.is_active.is_(True),
        ).order_by(User.name)
    ).all()
    return jsonify(
        {
            "data": [
                {
                    "id": doc.id,
                    "name": doc.name,
                    "role": doc.role,
                }
                for doc in doctors
            ]
        }
    )


@staff_blueprint.get("/staff")
@login_required
@require_permission("staff.read")
def list_staff():
    users = db.session.scalars(
        db.select(User)
        .where(User.clinic_id == g.current_user.clinic_id)
        .order_by(User.id.asc())
    ).all()
    return jsonify({"data": [_serialize_user(u) for u in users]})


@staff_blueprint.post("/staff")
@login_required
@require_permission("staff.create")
def create_staff():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return _error("Request body must be a JSON object.", 400)

    name = data.get("name")
    email = data.get("email")
    password = data.get("password")
    role = data.get("role")
    is_active = data.get("is_active", True)

    if not isinstance(name, str) or not name.strip():
        return _error("Staff member name is required.", 422)
    name = name.strip()

    if not isinstance(email, str) or not EMAIL_REGEX.match(email.strip()):
        return _error("A valid email address is required.", 422)
    email = email.strip().lower()

    password_error = validate_new_password(password)
    if password_error:
        return _error(password_error, 422)

    if not isinstance(role, str) or role not in VALID_STAFF_ROLES:
        return _error("Invalid staff role.", 400)

    if role == "head_doctor" and g.current_user.role != "super_admin":
        return _error(
            "Head doctors cannot create other head doctors. Only the platform Super Admin can assign head doctors.",
            403,
        )

    if not isinstance(is_active, bool):
        return _error("is_active must be a boolean.", 422)

    # Check for existing email across the entire database
    existing = db.session.scalar(
        db.select(User.id).where(func.lower(User.email) == email)
    )
    if existing is not None:
        return _error("A user with this email already exists.", 409)

    user = User(
        clinic_id=g.current_user.clinic_id,
        name=name,
        email=email,
        password_hash=hash_password(password),
        role=role,
        is_active=is_active,
    )
    db.session.add(user)
    try:
        db.session.flush()
        log_activity(
            action="staff_created",
            resource_type="staff",
            resource_id=user.id,
            clinic_id=user.clinic_id,
            details={
                "name": user.name,
                "role": user.role,
                "email": user.email,
            },
        )
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return _error("User could not be created.", 409)

    return jsonify({"data": _serialize_user(user)}), 201


@staff_blueprint.patch("/staff/<int:user_id>")
@login_required
@require_permission("staff.update")
def update_staff(user_id):
    target_user = _scoped_user(user_id)
    if target_user is None:
        return _error("Staff member not found.", 404)

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return _error("Request body must be a JSON object.", 400)

    if not data:
        return _error("At least one field is required to update.", 400)

    unsupported = set(data) - {"name", "email", "role", "is_active", "password"}
    if unsupported:
        return _error("Unsupported staff field.", 400)

    if "name" in data:
        if not isinstance(data["name"], str) or not data["name"].strip():
            return _error("Name must not be blank.", 422)
        target_user.name = data["name"].strip()

    if "email" in data:
        if not isinstance(data["email"], str) or not EMAIL_REGEX.match(data["email"].strip()):
            return _error("A valid email address is required.", 422)
        new_email = data["email"].strip().lower()
        if new_email != target_user.email:
            existing = db.session.scalar(
                db.select(User.id).where(
                    func.lower(User.email) == new_email,
                    User.id != target_user.id,
                )
            )
            if existing is not None:
                return _error("A user with this email already exists.", 409)
            target_user.email = new_email

    if "role" in data:
        new_role = data["role"]
        if not isinstance(new_role, str) or new_role not in VALID_STAFF_ROLES:
            return _error("Invalid staff role.", 400)
        if (
            new_role == "head_doctor"
            and target_user.role != "head_doctor"
            and g.current_user.role != "super_admin"
        ):
            return _error(
                "Head doctors cannot promote staff to head doctor. Only the platform Super Admin can assign head doctors.",
                403,
            )
        if (
            target_user.role == "head_doctor"
            and new_role != "head_doctor"
            and g.current_user.role != "super_admin"
        ):
            return _error("Head doctors cannot alter a head doctor's role.", 403)
        # Prevent demoting the last active head doctor
        if target_user.role == "head_doctor" and new_role != "head_doctor":
            other_heads = db.session.scalar(
                db.select(func.count(User.id)).where(
                    User.clinic_id == target_user.clinic_id,
                    User.role == "head_doctor",
                    User.is_active.is_(True),
                    User.id != target_user.id,
                )
            )
            if other_heads == 0:
                return _error("Cannot remove the only active head doctor in the clinic.", 422)
        target_user.role = new_role

    if "is_active" in data:
        new_status = data["is_active"]
        if not isinstance(new_status, bool):
            return _error("is_active must be a boolean.", 422)
        if target_user.role == "head_doctor" and not new_status:
            other_heads = db.session.scalar(
                db.select(func.count(User.id)).where(
                    User.clinic_id == target_user.clinic_id,
                    User.role == "head_doctor",
                    User.is_active.is_(True),
                    User.id != target_user.id,
                )
            )
            if other_heads == 0:
                return _error("Cannot deactivate the only active head doctor in the clinic.", 422)
        target_user.is_active = new_status
        if not new_status:
            revoke_user_sessions(target_user.id)

    if "password" in data:
        pwd = data["password"]
        password_error = validate_new_password(pwd)
        if password_error:
            return _error(password_error, 422)
        target_user.password_hash = hash_password(pwd)
        revoke_user_sessions(target_user.id)

    try:
        log_activity(
            action="staff_updated",
            resource_type="staff",
            resource_id=target_user.id,
            clinic_id=target_user.clinic_id,
            details={
                "name": target_user.name,
                "role": target_user.role,
                "is_active": target_user.is_active,
            },
        )
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return _error("Staff member could not be updated.", 409)

    return jsonify({"data": _serialize_user(target_user)})


@staff_blueprint.delete("/staff/<int:user_id>")
@login_required
@require_permission("staff.delete")
def delete_staff(user_id):
    target_user = _scoped_user(user_id)
    if target_user is None:
        return _error("Staff member not found.", 404)

    if target_user.id == g.current_user.id:
        return _error("You cannot delete your own account.", 400)

    if target_user.role == "head_doctor" and g.current_user.role != "super_admin":
        return _error("Head doctors cannot delete head doctor accounts.", 403)

    if target_user.role == "head_doctor":
        other_heads = db.session.scalar(
            db.select(func.count(User.id)).where(
                User.clinic_id == target_user.clinic_id,
                User.role == "head_doctor",
                User.is_active.is_(True),
                User.id != target_user.id,
            )
        )
        if other_heads == 0:
            return _error("Cannot delete the only active head doctor in the clinic.", 422)

    log_activity(
        action="staff_deleted",
        resource_type="staff",
        resource_id=target_user.id,
        clinic_id=target_user.clinic_id,
        details={
            "name": target_user.name,
            "role": target_user.role,
        },
    )
    db.session.delete(target_user)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return _error(
            "Staff member cannot be deleted because they have associated records. Deactivate the account instead.",
            409,
        )

    return "", 204
