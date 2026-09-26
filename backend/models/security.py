from datetime import datetime, timezone

from sqlalchemy import UniqueConstraint

from backend.extensions import db


def _utcnow():
    return datetime.now(timezone.utc)


class AuthThrottle(db.Model):
    """
    Shared (multi-worker) counters for brute-force protection and rate limiting.

    ``key_hash`` is a SHA-256 of the throttled subject (email, IP, email+IP, user id), so the
    table never stores raw emails or IP addresses.
    """

    __tablename__ = "auth_throttles"
    __table_args__ = (UniqueConstraint("scope", "key_hash", name="uq_auth_throttle_scope_key"),)

    id = db.Column(db.Integer, primary_key=True)
    scope = db.Column(db.String(40), nullable=False)
    key_hash = db.Column(db.String(64), nullable=False)
    count = db.Column(db.Integer, nullable=False, default=0)
    window_started_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utcnow)
    locked_until = db.Column(db.DateTime(timezone=True), nullable=True)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False, index=True)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class UserSession(db.Model):
    """
    Server-side record of every signed-in browser session.

    The signed session cookie only carries a random token; the database decides whether that
    token is still valid, so logout, password changes, and deactivation revoke sessions
    immediately instead of waiting for the cookie to expire.
    """

    __tablename__ = "user_sessions"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash = db.Column(db.String(64), nullable=False, unique=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utcnow)
    last_seen_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utcnow)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False, index=True)
    revoked_at = db.Column(db.DateTime(timezone=True), nullable=True)
    ip_address = db.Column(db.String(45), nullable=True)
    user_agent = db.Column(db.String(255), nullable=True)
