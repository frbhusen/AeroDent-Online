"""
Server-side brute-force protection, rate limiting, and session lifecycle.

All counters live in PostgreSQL (``auth_throttles``), so limits hold across every worker
process and survive restarts. Limits and behavior are documented in docs/SECURITY.md.

Login protection uses three independent scopes, each with exponential backoff:

* ``login_pair``    — one email from one IP. Stops a single attacker guessing one account.
* ``login_account`` — one email from any IP. Stops attackers rotating IP addresses.
  IPs that recently signed in to that account successfully ("trusted") are exempt from this
  scope, so a distributed attack cannot lock the real user out of their usual device.
* ``login_ip``      — one IP against any email. Stops username spraying / credential stuffing.
  Successful logins never reset it, so an attacker cannot clear it using their own account.

Every lock is temporary and capped; nothing here can lock an account permanently.
"""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from flask import current_app, request, session
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert

from backend.extensions import db
from backend.models.security import AuthThrottle, UserSession


# scope: (free failures before locking, base lock seconds, max lock seconds)
LOGIN_POLICIES = {
    "login_pair": (5, 30, 15 * 60),
    "login_account": (10, 60, 15 * 60),
    "login_ip": (30, 60, 60 * 60),
}
FAILURE_MEMORY = timedelta(hours=1)
TRUSTED_ORIGIN_DAYS = 30

MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128
_COMMON_PASSWORDS = frozenset(
    {
        "password", "password1", "password123", "12345678", "123456789", "1234567890",
        "qwerty123", "qwertyuiop", "11111111", "00000000", "iloveyou", "admin123",
        "letmein123", "welcome123", "abc12345", "aerodent", "aerodent123", "dentist123",
    }
)


def _now():
    return datetime.now(timezone.utc)


def _digest(*parts):
    return hashlib.sha256("\x1f".join(str(p) for p in parts).encode("utf-8")).hexdigest()


def normalize_email(email):
    return (email or "").strip().lower()


def validate_new_password(password):
    """Returns an error message, or None when the password is acceptable."""
    if not isinstance(password, str):
        return "Password is required."
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"Password must be at least {MIN_PASSWORD_LENGTH} characters long."
    if len(password) > MAX_PASSWORD_LENGTH:
        return f"Password must be at most {MAX_PASSWORD_LENGTH} characters long."
    if not password.strip():
        return "Password must not be blank."
    if password.lower() in _COMMON_PASSWORDS:
        return "This password is too common. Choose a less predictable password."
    return None


# ---------------------------------------------------------------------------
# Throttle rows
# ---------------------------------------------------------------------------

def _row(scope, key_hash, *, lock=True):
    """Fetches (creating if needed) and row-locks the throttle row for this subject."""
    now = _now()
    db.session.execute(
        insert(AuthThrottle)
        .values(
            scope=scope,
            key_hash=key_hash,
            count=0,
            window_started_at=now,
            expires_at=now + FAILURE_MEMORY,
            updated_at=now,
        )
        .on_conflict_do_nothing(constraint="uq_auth_throttle_scope_key")
    )
    query = select(AuthThrottle).where(AuthThrottle.scope == scope, AuthThrottle.key_hash == key_hash)
    if lock:
        query = query.with_for_update()
    return db.session.scalar(query)


def _peek(scope, key_hash):
    return db.session.scalar(
        select(AuthThrottle).where(AuthThrottle.scope == scope, AuthThrottle.key_hash == key_hash)
    )


def _remaining_lock(row, now):
    if row is None or row.locked_until is None or row.locked_until <= now:
        return 0
    return int((row.locked_until - now).total_seconds()) + 1


def _backoff_seconds(policy, failures):
    free, base, cap = policy
    if failures < free:
        return 0
    return min(cap, base * (2 ** (failures - free)))


def cleanup_expired():
    """Opportunistic cleanup; cheap because both columns are indexed."""
    now = _now()
    db.session.execute(delete(AuthThrottle).where(AuthThrottle.expires_at < now))
    db.session.execute(
        delete(UserSession).where(UserSession.expires_at < now - timedelta(days=1))
    )


# ---------------------------------------------------------------------------
# Login throttling
# ---------------------------------------------------------------------------

def _login_keys(email, ip):
    email = normalize_email(email)
    return {
        "login_pair": _digest("pair", email, ip),
        "login_account": _digest("account", email),
        "login_ip": _digest("ip", ip),
    }


def _is_trusted_origin(email, ip, now):
    row = _peek("trusted_origin", _digest("trusted", normalize_email(email), ip))
    return row is not None and row.expires_at > now


def login_retry_after(email, ip):
    """Seconds the caller must wait before a login attempt is even evaluated (0 = allowed)."""
    now = _now()
    keys = _login_keys(email, ip)
    trusted = _is_trusted_origin(email, ip, now)
    wait = 0
    for scope, key_hash in keys.items():
        if scope == "login_account" and trusted:
            continue
        wait = max(wait, _remaining_lock(_peek(scope, key_hash), now))
    return wait


def record_login_failure(email, ip):
    """Counts a failed attempt against every scope and returns the resulting wait (seconds)."""
    now = _now()
    wait = 0
    trusted = _is_trusted_origin(email, ip, now)
    for scope, key_hash in _login_keys(email, ip).items():
        row = _row(scope, key_hash)
        if row.expires_at <= now:
            row.count = 0
            row.window_started_at = now
            row.locked_until = None
        row.count += 1
        row.expires_at = now + FAILURE_MEMORY
        lock_for = _backoff_seconds(LOGIN_POLICIES[scope], row.count)
        if lock_for:
            row.locked_until = now + timedelta(seconds=lock_for)
            row.expires_at = max(row.expires_at, row.locked_until + FAILURE_MEMORY)
            if not (scope == "login_account" and trusted):
                wait = max(wait, lock_for)
    return wait


def record_login_success(email, ip):
    now = _now()
    keys = _login_keys(email, ip)
    db.session.execute(
        delete(AuthThrottle).where(
            AuthThrottle.scope.in_(["login_pair", "login_account"]),
            AuthThrottle.key_hash.in_([keys["login_pair"], keys["login_account"]]),
        )
    )
    trusted = _row("trusted_origin", _digest("trusted", normalize_email(email), ip))
    trusted.count = 1
    trusted.expires_at = now + timedelta(days=TRUSTED_ORIGIN_DAYS)


# ---------------------------------------------------------------------------
# Generic limits for other sensitive endpoints
# ---------------------------------------------------------------------------

def rate_limited(scope, subject, limit, window_seconds):
    """
    Fixed-window counter. Returns 0 if the call is allowed (and counts it), otherwise the
    number of seconds until the window resets.
    """
    now = _now()
    row = _row(scope, _digest(scope, subject))
    if row.expires_at <= now:
        row.count = 0
        row.window_started_at = now
        row.expires_at = now + timedelta(seconds=window_seconds)
    if row.count >= limit:
        return int((row.expires_at - now).total_seconds()) + 1
    row.count += 1
    return 0


def failure_lock_wait(scope, subject):
    return _remaining_lock(_peek(scope, _digest(scope, subject)), _now())


def record_failure(scope, subject, policy=(5, 60, 15 * 60)):
    now = _now()
    row = _row(scope, _digest(scope, subject))
    if row.expires_at <= now:
        row.count = 0
        row.locked_until = None
    row.count += 1
    row.expires_at = now + FAILURE_MEMORY
    lock_for = _backoff_seconds(policy, row.count)
    if lock_for:
        row.locked_until = now + timedelta(seconds=lock_for)
        row.expires_at = max(row.expires_at, row.locked_until + FAILURE_MEMORY)
    return lock_for


def clear_failures(scope, subject):
    db.session.execute(
        delete(AuthThrottle).where(AuthThrottle.scope == scope, AuthThrottle.key_hash == _digest(scope, subject))
    )


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------

def _idle_timeout():
    return current_app.config["SESSION_IDLE_TIMEOUT"]


def start_session(user, ip):
    """Issues a brand-new session (prevents fixation: any previous cookie content is dropped)."""
    token = secrets.token_urlsafe(32)
    now = _now()
    db.session.add(
        UserSession(
            user_id=user.id,
            token_hash=_digest("session", token),
            created_at=now,
            last_seen_at=now,
            expires_at=now + current_app.config["SESSION_ABSOLUTE_TIMEOUT"],
            ip_address=ip,
            user_agent=(request.headers.get("User-Agent") or "")[:255] or None,
        )
    )
    session.clear()
    session.permanent = True
    session["user_id"] = user.id
    session["sid"] = token


def current_session_record(user_id, *, touch=True):
    """
    Returns the live UserSession for the cookie, or None if missing/expired/revoked.
    ``touch=False`` checks validity without counting as activity (used by the status poll,
    which must not keep an idle session alive).
    """
    token = session.get("sid")
    if not isinstance(token, str) or not token:
        return None
    record = db.session.scalar(
        select(UserSession).where(
            UserSession.token_hash == _digest("session", token),
            UserSession.user_id == user_id,
        )
    )
    now = _now()
    if (
        record is None
        or record.revoked_at is not None
        or record.expires_at <= now
        or record.last_seen_at + _idle_timeout() <= now
    ):
        return None
    if touch and now - record.last_seen_at > timedelta(seconds=60):
        record.last_seen_at = now
        db.session.commit()
    return record


def revoke_current_session():
    token = session.get("sid")
    if isinstance(token, str) and token:
        record = db.session.scalar(select(UserSession).where(UserSession.token_hash == _digest("session", token)))
        if record is not None and record.revoked_at is None:
            record.revoked_at = _now()
    session.clear()


def revoke_user_sessions(user_id, *, keep_current=False):
    """Revokes every live session of a user (password change, deactivation, deletion...)."""
    query = select(UserSession).where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
    current = session.get("sid") if keep_current else None
    current_hash = _digest("session", current) if isinstance(current, str) and current else None
    now = _now()
    for record in db.session.scalars(query):
        if current_hash and record.token_hash == current_hash:
            continue
        record.revoked_at = now


def session_seconds_remaining(record):
    now = _now()
    idle_left = (record.last_seen_at + _idle_timeout() - now).total_seconds()
    absolute_left = (record.expires_at - now).total_seconds()
    return max(0, int(min(idle_left, absolute_left)))
