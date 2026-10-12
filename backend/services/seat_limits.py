"""Per-clinic staff seat limits, set by the platform Super Admin.

``Clinic.max_doctors`` / ``Clinic.max_secretaries`` of ``None`` mean "unlimited".
Head doctors are not counted; only active ``doctor`` and ``secretary`` accounts use a seat.
"""

from sqlalchemy import func

from backend.extensions import db
from backend.models import Clinic, User

# role -> (Clinic limit attribute, error message when the limit is reached)
_SEAT_ROLES = {
    "doctor": (
        "max_doctors",
        "Your plan allows {limit} doctor(s). Ask the platform administrator to raise the limit.",
    ),
    "secretary": (
        "max_secretaries",
        "Your plan allows {limit} secretary account(s). Ask the platform administrator to raise the limit.",
    ),
}


def count_active_seats(clinic_id, role, exclude_user_id=None):
    query = db.select(func.count(User.id)).where(
        User.clinic_id == clinic_id,
        User.role == role,
        User.is_active.is_(True),
    )
    if exclude_user_id is not None:
        query = query.where(User.id != exclude_user_id)
    return db.session.scalar(query) or 0


def seat_limit_error(clinic_id, role, exclude_user_id=None):
    """Return an error message if one more active ``role`` account would exceed the clinic's limit."""
    if role not in _SEAT_ROLES:
        return None
    attr, message = _SEAT_ROLES[role]
    clinic = db.session.get(Clinic, clinic_id)
    limit = getattr(clinic, attr, None) if clinic else None
    if limit is None:
        return None
    if count_active_seats(clinic_id, role, exclude_user_id) >= limit:
        return message.format(limit=limit)
    return None


def seat_usage(clinic_id):
    clinic = db.session.get(Clinic, clinic_id)
    return {
        "doctors": {
            "used": count_active_seats(clinic_id, "doctor"),
            "limit": clinic.max_doctors if clinic else None,
        },
        "secretaries": {
            "used": count_active_seats(clinic_id, "secretary"),
            "limit": clinic.max_secretaries if clinic else None,
        },
    }


def parse_seat_limit(raw):
    """Parse an admin-supplied limit. Returns (value, error); blank/None means unlimited."""
    if raw is None or raw == "":
        return None, None
    if isinstance(raw, bool):
        return None, "Seat limits must be whole numbers."
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None, "Seat limits must be whole numbers."
    if value < 0 or value > 1000:
        return None, "Seat limits must be between 0 and 1000."
    return value, None
