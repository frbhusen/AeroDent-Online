"""First-run setup of the standalone (desktop) edition.

The database starts empty. The first time the app opens, the doctor creates the clinic and the head
doctor account; after that this endpoint refuses to do anything, so it can never be used to add
another account or overwrite the clinic.
"""

import re

from flask import Blueprint, jsonify, request

from backend.auth.routes import _user_response
from backend.auth.service import hash_password
from backend.extensions import db
from backend.models import Clinic, User
from backend.services.audit import get_client_ip, log_activity
from backend.services.auth_security import start_session, validate_new_password
from backend.services.countries import get_country, list_countries

setup_blueprint = Blueprint("setup", __name__, url_prefix="/api/setup")

EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _error(message, status, field=None):
    payload = {"error": message}
    if field:
        payload["field"] = field
    return jsonify(payload), status


def _is_set_up():
    return db.session.scalar(db.select(db.func.count(User.id))) > 0


@setup_blueprint.get("/countries")
def setup_countries():
    # Static reference data, needed by the setup form before anyone can sign in.
    return jsonify({"data": list_countries()})


@setup_blueprint.get("/status")
def setup_status():
    return jsonify({"needed": not _is_set_up()})


@setup_blueprint.post("")
def run_setup():
    if _is_set_up():
        return _error("This installation is already set up.", 409)

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return _error("Request body must be a JSON object.", 400)

    def text(field, limit):
        value = data.get(field)
        return value.strip()[:limit] if isinstance(value, str) else ""

    clinic_name = text("clinic_name", 150)
    doctor_name = text("doctor_name", 150)
    email = text("email", 255).lower()
    password = data.get("password")
    country = data.get("country") or None
    currency = text("currency", 10) or "SYR"

    if not clinic_name:
        return _error("Clinic name is required.", 422, "clinic_name")
    if not doctor_name:
        return _error("Doctor name is required.", 422, "doctor_name")
    if not EMAIL_REGEX.match(email):
        return _error("A valid email address is required.", 422, "email")
    password_error = validate_new_password(password)
    if password_error:
        return _error(password_error, 422, "password")
    if country is not None and get_country(country) is None:
        return _error("Unknown country.", 422, "country")

    clinic = Clinic(
        name=clinic_name,
        currency=currency,
        country=country,
        is_active=True,
        subscription_status="active",
    )
    db.session.add(clinic)
    db.session.flush()
    user = User(
        clinic_id=clinic.id,
        name=doctor_name,
        email=email,
        password_hash=hash_password(password),
        role="head_doctor",
        is_active=True,
    )
    db.session.add(user)
    db.session.flush()
    log_activity(
        action="standalone_setup_completed",
        resource_type="clinic",
        resource_id=clinic.id,
        clinic_id=clinic.id,
        user_id=user.id,
        user_name=user.name,
        user_role=user.role,
        details={"clinic_name": clinic.name},
    )
    start_session(user, get_client_ip() or "local")
    db.session.commit()
    return jsonify({"user": _user_response(user)}), 201
