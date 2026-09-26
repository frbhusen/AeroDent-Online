from datetime import datetime, timezone

from backend.extensions import db


class TrialRequest(db.Model):
    """
    A prospective clinic asking for a 14-day trial (placeholder for the future lead workflow).

    Platform-level data: it belongs to no clinic and is only visible to the platform owner.
    The requester's IP is stored only as a salted hash for abuse investigation.
    """

    __tablename__ = "trial_requests"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(30), nullable=False)
    email = db.Column(db.String(255), nullable=False)
    message = db.Column(db.Text, nullable=True)
    language = db.Column(db.String(5), nullable=False, default="en")
    status = db.Column(db.String(20), nullable=False, default="new")
    ip_hash = db.Column(db.String(64), nullable=True)
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )
