from datetime import datetime, timedelta, timezone
from functools import wraps

from flask import Blueprint, current_app, g, jsonify, request, session
from sqlalchemy import func

from backend.extensions import db
from backend.models import User, Clinic
from backend.auth.service import verify_password, hash_password
from backend.services.audit import log_activity, get_client_ip
from backend.services.auth_security import (
    cleanup_expired,
    clear_failures,
    current_session_record,
    failure_lock_wait,
    login_retry_after,
    normalize_email,
    rate_limited,
    record_failure,
    record_login_failure,
    record_login_success,
    revoke_current_session,
    revoke_user_sessions,
    start_session,
    validate_new_password,
)


auth_blueprint = Blueprint("auth", __name__, url_prefix="/api/auth")

# Verified against when the email is unknown so both paths cost the same scrypt time and the
# response timing does not reveal whether an account exists.
_DUMMY_PASSWORD_HASH = hash_password("aerodent-timing-equalizer-not-a-real-password")


def _too_many(retry_after, message="Too many attempts. Please wait before trying again."):
    response = jsonify({"error": message, "retry_after": retry_after})
    response.status_code = 429
    response.headers["Retry-After"] = str(retry_after)
    return response


def _same_origin_request():
    expected_origin = request.host_url.rstrip("/")
    origin = request.headers.get("Origin")

    if origin and origin.rstrip("/") != expected_origin:
        return False

    referer = request.headers.get("Referer")
    if not origin and referer and not referer.startswith(f"{expected_origin}/"):
        return False

    return True


def _user_response(user):
    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "role": user.role,
        "clinic_id": user.clinic_id,
    }


def _invalid_credentials():
    session.clear()
    return jsonify({"error": "Invalid email or password."}), 401


def _resolve_session_user():
    """Loads the user for the current cookie if (and only if) its server-side session is live."""
    user_id = session.get("user_id")
    if not isinstance(user_id, int):
        return None
    user = db.session.get(User, user_id)
    if user is None or current_session_record(user.id) is None:
        session.clear()
        return None
    return user


def evaluate_user_access(user):
    """
    Evaluates whether a user is allowed to access the system.
    Enforces cascade rules:
    - Inactive user -> denied.
    - Super admin -> global access allowed.
    - Clinic inactive / suspended -> all clinic users denied.
    - Clinic subscription expired -> all clinic users denied.
    - Clinic head doctor inactive -> all clinic users denied (cascade lock).
    """
    if user is None or not user.is_active:
        return False, "Your account has been deactivated.", 401

    if user.role == "super_admin":
        return True, "", 200

    clinic = user.clinic
    if clinic is None or not clinic.is_active:
        return (
            False,
            "Clinic account has been deactivated. Please contact platform support.",
            403,
        )

    if clinic.subscription_status in {"suspended", "cancelled"}:
        return (
            False,
            "Clinic subscription has been suspended. Please contact platform support.",
            403,
        )

    if (
        clinic.subscription_expires_at
        and clinic.subscription_expires_at < datetime.now(timezone.utc)
    ):
        return (
            False,
            "Clinic subscription has expired. Please contact platform support to renew.",
            403,
        )

    # Cascade Rule: If clinic head doctor is deactivated, entire clinic is locked out
    has_inactive_head = db.session.scalar(
        db.select(func.count(User.id)).where(
            User.clinic_id == user.clinic_id,
            User.role == "head_doctor",
            User.is_active.is_(False),
        )
    )
    has_active_head = db.session.scalar(
        db.select(func.count(User.id)).where(
            User.clinic_id == user.clinic_id,
            User.role == "head_doctor",
            User.is_active.is_(True),
        )
    )
    if has_inactive_head > 0 and has_active_head == 0:
        return (
            False,
            "Clinic head doctor account is inactive. Access for this entire clinic is disabled.",
            403,
        )

    return True, "", 200


def get_current_user():
    user = _resolve_session_user()
    if user is None:
        return None

    allowed, _, _ = evaluate_user_access(user)
    if not allowed:
        session.clear()
        return None

    return user


def login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        user = _resolve_session_user()
        if user is None:
            return jsonify({"error": "Authentication required."}), 401

        allowed, error_msg, status_code = evaluate_user_access(user)
        if not allowed:
            session.clear()
            return jsonify({"error": error_msg}), status_code

        g.current_user = user
        g.current_clinic = user.clinic
        return view(*args, **kwargs)

    return wrapped_view


@auth_blueprint.before_request
def protect_state_changing_requests():
    if request.method in {"POST", "PUT", "PATCH", "DELETE"} and not _same_origin_request():
        return jsonify({"error": "Cross-origin request rejected."}), 403

    return None


@auth_blueprint.post("/login")
def login():
    ip = get_client_ip() or "unknown"
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Request body must be JSON."}), 400

    email = data.get("email")
    password = data.get("password")
    if not isinstance(email, str) or not isinstance(password, str) or len(email) > 255 or len(password) > 1024:
        return _invalid_credentials()

    normalized_email = normalize_email(email)
    retry_after = login_retry_after(normalized_email, ip)
    if retry_after:
        db.session.rollback()
        return _too_many(retry_after, "Too many failed sign-in attempts. Please wait before trying again.")

    user = db.session.scalar(
        db.select(User).where(func.lower(User.email) == normalized_email)
    )
    password_ok = verify_password(password, user.password_hash if user else _DUMMY_PASSWORD_HASH)

    if user is None or not password_ok:
        wait = record_login_failure(normalized_email, ip)
        log_activity(
            action="login_failed",
            resource_type="auth",
            clinic_id=user.clinic_id if user else None,
            user_id=user.id if user else None,
            details={"reason": "invalid_credentials", "throttled_seconds": wait},
        )
        db.session.commit()
        session.clear()
        if wait:
            return _too_many(wait, "Too many failed sign-in attempts. Please wait before trying again.")
        return _invalid_credentials()

    allowed, error_msg, status_code = evaluate_user_access(user)
    if not allowed:
        # The password was correct, so this reveals nothing to someone who does not own it.
        db.session.commit()
        session.clear()
        return jsonify({"error": error_msg}), status_code

    record_login_success(normalized_email, ip)
    cleanup_expired()
    start_session(user, ip)

    log_activity(
        action="user_login",
        resource_type="auth",
        resource_id=user.id,
        clinic_id=user.clinic_id,
        user_id=user.id,
        user_name=user.name,
        user_role=user.role,
        details={"email": user.email},
    )
    db.session.commit()

    return jsonify({"user": _user_response(user)})


@auth_blueprint.post("/register")
def register_clinic():
    if not current_app.config.get("ALLOW_SELF_REGISTRATION"):
        return jsonify({"error": "Self-service registration is disabled. Please request a trial."}), 403

    ip = get_client_ip() or "unknown"
    retry_after = rate_limited("register_ip", ip, limit=5, window_seconds=3600)
    db.session.commit()
    if retry_after:
        return _too_many(retry_after, "Too many registration attempts. Please try again later.")

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Request body must be JSON."}), 400
    clinic_name = (data.get("clinic_name") or "").strip()
    head_doctor_name = (data.get("head_doctor_name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    phone = (data.get("phone") or "").strip()

    if not clinic_name or not head_doctor_name or not email or not password:
        return jsonify({"error": "Clinic name, doctor name, email, and password are required."}), 400

    if len(clinic_name) > 150 or len(head_doctor_name) > 150 or len(email) > 255 or len(phone) > 50:
        return jsonify({"error": "One or more fields are too long."}), 400
    if "@" not in email or " " in email:
        return jsonify({"error": "A valid email address is required."}), 400
    password_error = validate_new_password(password)
    if password_error:
        return jsonify({"error": password_error}), 400

    existing_user = db.session.scalar(db.select(User).where(func.lower(User.email) == email))
    if existing_user:
        return jsonify({"error": "An account with this email already exists."}), 409

    trial_expires = datetime.now(timezone.utc) + timedelta(days=14)
    clinic = Clinic(
        name=clinic_name,
        phone=phone or None,
        is_active=True,
        subscription_status="trial",
        subscription_expires_at=trial_expires,
    )
    db.session.add(clinic)
    db.session.flush()

    user = User(
        clinic_id=clinic.id,
        name=head_doctor_name,
        email=email,
        password_hash=hash_password(password),
        role="head_doctor",
        is_active=True,
    )
    db.session.add(user)
    db.session.flush()

    log_activity(
        action="clinic_registered",
        resource_type="clinic",
        resource_id=clinic.id,
        clinic_id=clinic.id,
        user_id=user.id,
        user_name=user.name,
        user_role=user.role,
        details={"clinic_name": clinic.name, "trial_days": 14},
    )

    start_session(user, ip)
    db.session.commit()

    return jsonify({
        "message": "Clinic trial registered successfully.",
        "user": _user_response(user),
        "clinic": {
            "id": clinic.id,
            "name": clinic.name,
            "subscription_status": clinic.subscription_status,
            "subscription_expires_at": clinic.subscription_expires_at.isoformat(),
        },
    }), 201


@auth_blueprint.get("/me")
@login_required
def current_user():
    return jsonify({"user": _user_response(g.current_user)})


@auth_blueprint.post("/logout")
def logout():
    user = get_current_user()
    if user:
        log_activity(
            action="user_logout",
            resource_type="auth",
            resource_id=user.id,
            clinic_id=user.clinic_id,
            user_id=user.id,
            user_name=user.name,
            user_role=user.role,
        )
    revoke_current_session()
    db.session.commit()
    return jsonify({"message": "Logged out."})


@auth_blueprint.post("/change-password")
@login_required
def change_password():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Request body must be JSON."}), 400
    current_password = data.get("current_password")
    new_password = data.get("new_password")

    if not isinstance(current_password, str) or not isinstance(new_password, str) or not current_password or not new_password:
        return jsonify({"error": "Current password and new password are required."}), 400

    user = g.current_user
    # A stolen session must not be usable to brute-force the account password.
    retry_after = failure_lock_wait("password_change", user.id)
    if retry_after:
        return _too_many(retry_after)

    if len(current_password) > 1024 or not verify_password(current_password, user.password_hash):
        wait = record_failure("password_change", user.id, policy=(5, 60, 30 * 60))
        log_activity(
            action="password_change_failed",
            resource_type="auth",
            resource_id=user.id,
            details={"reason": "wrong_current_password"},
        )
        db.session.commit()
        if wait:
            return _too_many(wait)
        return jsonify({"error": "Current password is incorrect."}), 400

    password_error = validate_new_password(new_password)
    if password_error:
        return jsonify({"error": password_error}), 400

    if current_password == new_password:
        return jsonify({"error": "New password must be different from current password."}), 400

    user.password_hash = hash_password(new_password)
    clear_failures("password_change", user.id)
    # Sign out every other device; the current one stays signed in.
    revoke_user_sessions(user.id, keep_current=True)
    log_activity(
        action="password_changed",
        resource_type="auth",
        resource_id=user.id,
        clinic_id=user.clinic_id,
        user_id=user.id,
        user_name=user.name,
        user_role=user.role,
    )
    db.session.commit()

    return jsonify({"message": "Password changed successfully."})
