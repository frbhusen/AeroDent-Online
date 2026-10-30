"""Self-service 14-day trial accounts.

A trial is a normal clinic (``subscription_status="trial"``, expiring after ``TRIAL_DAYS``) with one
head-doctor account whose credentials follow a fixed pattern, using the user's own sequential id:

    email:    {username}_{user_id}@aerodent.com
    password: {username}_{user_id}!
"""

import re
import secrets
from datetime import datetime, timedelta, timezone

from backend.auth.service import hash_password
from backend.extensions import db
from backend.models import Clinic, User

TRIAL_DAYS = 14
EMAIL_DOMAIN = "aerodent.com"
TRIAL_MAX_DOCTORS = 3
TRIAL_MAX_SECRETARIES = 3

# English letters, digits and underscores; starts with a letter; no spaces. Stored lowercase.
USERNAME_RE = re.compile(r"^[a-z][a-z0-9_]{2,29}$")
USERNAME_ERROR = (
    "Username must be 3-30 English letters, digits or underscores, start with a letter and contain no spaces."
)


def normalize_username(value):
    """Returns (username, None) or (None, error message)."""
    if not isinstance(value, str):
        return None, USERNAME_ERROR
    username = value.strip().lower()
    if not USERNAME_RE.match(username):
        return None, USERNAME_ERROR
    return username, None


def create_trial_account(*, name, clinic_name, phone, username):
    """Creates the clinic and its head doctor inside the caller's transaction (no commit).

    The user id comes from the database sequence, so ids are sequential; the email and password are
    derived from it after the first flush. Returns (clinic, user, email, password).
    """
    clinic = Clinic(
        name=clinic_name,
        phone=phone or None,
        is_active=True,
        subscription_status="trial",
        subscription_expires_at=datetime.now(timezone.utc) + timedelta(days=TRIAL_DAYS),
        max_doctors=TRIAL_MAX_DOCTORS,
        max_secretaries=TRIAL_MAX_SECRETARIES,
    )
    db.session.add(clinic)
    db.session.flush()

    user = User(
        clinic_id=clinic.id,
        name=name,
        # Placeholder until the id exists; replaced below within the same transaction.
        email=f"pending-{secrets.token_hex(8)}@{EMAIL_DOMAIN}",
        password_hash=hash_password(secrets.token_urlsafe(24)),
        role="head_doctor",
        is_active=True,
    )
    db.session.add(user)
    db.session.flush()

    email = f"{username}_{user.id}@{EMAIL_DOMAIN}"
    password = f"{username}_{user.id}!"
    user.email = email
    user.password_hash = hash_password(password)
    db.session.flush()
    return clinic, user, email, password
