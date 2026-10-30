"""
"Ask for a 14-day trial" flow.

The request-trial page is not a public navigation destination. It is only served when the
browser presents a short-lived, signed, HTTP-only "trial intent" cookie, which is issued by
POST /api/trial/intent when the user clicks the button on the sign-in page (a same-origin
POST, protected by the global Origin/Referer check). Typing /request-trial directly, or
following an old link after the cookie expires, redirects to the sign-in page.

This is flow gating, not an access-control boundary: the page contains no private data.
"""

import hashlib
import re

from flask import Blueprint, current_app, jsonify, redirect, request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from backend.extensions import db
from backend.models.trial import TrialRequest
from backend.services.audit import get_client_ip, log_activity
from backend.services.auth_security import rate_limited, start_session
from backend.services.trial_accounts import TRIAL_DAYS, create_trial_account, normalize_username


trial_blueprint = Blueprint("trial", __name__)

INTENT_COOKIE = "aerodent_trial_intent"
INTENT_MAX_AGE = 30 * 60
PAGE_PATH = "/request-trial"

EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[^@\s]{2,}$")
PHONE_RE = re.compile(r"^\+?[0-9 ()\-]{6,30}$")
FIELDS = frozenset({"name", "phone", "email", "message", "language", "website", "username", "clinic"})
SIGNUP_FIELDS = frozenset({"name", "phone", "message", "language", "website", "username", "clinic", "location"})
SIGNUP_MESSAGE = "Your trial account is ready."


def _serializer():
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt="aerodent-trial-intent")


def _has_valid_intent():
    token = request.cookies.get(INTENT_COOKIE)
    if not token:
        return False
    try:
        return _serializer().loads(token, max_age=INTENT_MAX_AGE) == "trial-request"
    except (BadSignature, SignatureExpired):
        return False


def _error(message, status, field=None):
    payload = {"error": message}
    if field:
        payload["field"] = field
    return jsonify(payload), status


@trial_blueprint.post("/api/trial/intent")
def create_trial_intent():
    ip = get_client_ip() or "unknown"
    retry_after = rate_limited("trial_intent_ip", ip, limit=30, window_seconds=3600)
    db.session.commit()
    if retry_after:
        return _error("Too many requests. Please try again later.", 429)

    response = jsonify({"redirect": PAGE_PATH})
    response.set_cookie(
        INTENT_COOKIE,
        _serializer().dumps("trial-request"),
        max_age=INTENT_MAX_AGE,
        httponly=True,
        secure=current_app.config.get("SESSION_COOKIE_SECURE", False),
        samesite="Strict",
        path="/",
    )
    return response


@trial_blueprint.get(PAGE_PATH)
def trial_page():
    if not _has_valid_intent():
        return redirect("/", code=302)
    assets = current_app.extensions["aerodent_assets"]
    return assets.serve_page("trial.html")


@trial_blueprint.post("/api/trial/requests")
def submit_trial_request():
    if not _has_valid_intent():
        return _error("This form has expired. Please return to the sign-in page and try again.", 403)

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return _error("Request body must be a JSON object.", 400)
    if set(data) - FIELDS:
        return _error("Unsupported field.", 400)

    # Honeypot: real users never see or fill this field.
    if data.get("website"):
        return jsonify({"message": "Thank you. We will contact you soon."}), 201

    values = {}
    for field in ("name", "phone", "email", "message", "clinic"):
        value = data.get(field)
        if value is not None and not isinstance(value, str):
            return _error(f"{field} must be text.", 422, field)
        values[field] = (value or "").strip()

    if not 2 <= len(values["name"]) <= 120:
        return _error("Please enter your full name.", 422, "name")
    if not PHONE_RE.match(values["phone"]) or sum(ch.isdigit() for ch in values["phone"]) < 6:
        return _error("Please enter a valid phone number.", 422, "phone")
    if len(values["email"]) > 255 or not EMAIL_RE.match(values["email"]):
        return _error("Please enter a valid email address.", 422, "email")
    if len(values["message"]) > 1000:
        return _error("The message must be at most 1000 characters.", 422, "message")
    if len(values["clinic"]) > 150:
        return _error("The clinic name must be at most 150 characters.", 422, "clinic")
    username, username_error = normalize_username(data.get("username"))
    if username_error:
        return _error(username_error, 422, "username")

    ip = get_client_ip() or "unknown"
    retry_after = rate_limited("trial_request_ip", ip, limit=5, window_seconds=3600)
    if retry_after:
        db.session.commit()
        return _error("Too many requests. Please try again later.", 429)

    language = data.get("language") if data.get("language") in ("en", "ar") else "en"
    return _create_trial(
        name=values["name"],
        phone=values["phone"],
        contact_email=values["email"].lower(),
        message=values["message"],
        clinic_name=values["clinic"],
        username=username,
        language=language,
        ip=ip,
    )


def _create_trial(*, name, phone, contact_email, message, clinic_name, username, language, ip):
    """Records the request and creates the trial clinic + head doctor in one transaction."""
    clinic, user, email, password = create_trial_account(
        name=name,
        clinic_name=clinic_name or f"{name} Clinic",
        phone=phone,
        username=username,
    )
    trial_request = TrialRequest(
        name=name,
        phone=phone,
        email=contact_email or email,
        message=message or None,
        language=language,
        status="converted",
        username=username,
        created_clinic_id=clinic.id,
        ip_hash=hashlib.sha256(f"{current_app.config['SECRET_KEY']}|{ip}".encode()).hexdigest(),
    )
    db.session.add(trial_request)
    db.session.flush()
    # Audit entries carry no personal details or credentials.
    log_activity(
        action="trial_requested",
        resource_type="trial_request",
        resource_id=trial_request.id,
        clinic_id=None,
        user_id=None,
        details={"language": language},
    )
    log_activity(
        action="trial_account_created",
        resource_type="clinic",
        resource_id=clinic.id,
        clinic_id=clinic.id,
        user_id=user.id,
        details={"trial_days": TRIAL_DAYS},
    )
    # Sign the new head doctor in right away, so "Sign in" after the request opens the dashboard
    # without retyping the generated credentials.
    start_session(user, ip)
    log_activity(
        action="user_login",
        resource_type="auth",
        resource_id=user.id,
        clinic_id=clinic.id,
        user_id=user.id,
        user_name=user.name,
        user_role=user.role,
        details={"email": email, "via": "trial_signup"},
    )
    db.session.commit()
    return (
        jsonify(
            {
                "message": SIGNUP_MESSAGE,
                "data": {
                    "email": email,
                    "password": password,
                    "clinic_name": clinic.name,
                    "trial_days": TRIAL_DAYS,
                },
            }
        ),
        201,
    )


@trial_blueprint.post("/api/trial/signup")
def trial_signup():
    """Public sign-up used by the landing page's "ask for a demo" form (no intent cookie needed)."""
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return _error("Request body must be a JSON object.", 400)
    if set(data) - SIGNUP_FIELDS:
        return _error("Unsupported field.", 400)

    # Honeypot: real users never see or fill this field.
    if data.get("website"):
        return jsonify({"message": SIGNUP_MESSAGE}), 201

    values = {}
    for field in ("name", "phone", "message", "clinic", "location"):
        value = data.get(field)
        if value is not None and not isinstance(value, str):
            return _error(f"{field} must be text.", 422, field)
        values[field] = (value or "").strip()

    if not 2 <= len(values["name"]) <= 120:
        return _error("Please enter your full name.", 422, "name")
    if not 2 <= len(values["clinic"]) <= 150:
        return _error("Please enter the clinic name.", 422, "clinic")
    if not PHONE_RE.match(values["phone"]) or sum(ch.isdigit() for ch in values["phone"]) < 6:
        return _error("Please enter a valid phone number.", 422, "phone")
    if len(values["message"]) > 1000:
        return _error("The message must be at most 1000 characters.", 422, "message")
    username, username_error = normalize_username(data.get("username"))
    if username_error:
        return _error(username_error, 422, "username")

    ip = get_client_ip() or "unknown"
    retry_after = rate_limited("trial_signup_ip", ip, limit=5, window_seconds=3600)
    if retry_after:
        db.session.commit()
        return _error("Too many requests. Please try again later.", 429)

    language = data.get("language") if data.get("language") in ("en", "ar") else "ar"
    message = values["message"]
    if values["location"]:
        message = f"[{values['location']}] {message}".strip()
    return _create_trial(
        name=values["name"],
        phone=values["phone"],
        contact_email="",
        message=message,
        clinic_name=values["clinic"],
        username=username,
        language=language,
        ip=ip,
    )
