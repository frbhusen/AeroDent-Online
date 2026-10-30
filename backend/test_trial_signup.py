import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from backend.app import app
from backend.extensions import db
from backend.models import AuditLog, AuthThrottle, Clinic, TrialRequest, User


def _client(ip):
    client = app.test_client()
    client.environ_base["REMOTE_ADDR"] = ip
    return client


def _payload(username, **overrides):
    payload = {
        "name": "Dr. Sami Haddad",
        "clinic": "Smile Clinic",
        "phone": "+963 944 123 456",
        "location": "Damascus",
        "username": username,
        "language": "ar",
    }
    payload.update(overrides)
    return payload


def run_trial_signup_tests():
    suffix = uuid4().hex[:6]
    ctx = app.app_context()
    ctx.push()
    created_clinics = []
    try:
        db.session.query(AuthThrottle).delete()
        db.session.commit()
        client = _client("10.30.0.1")

        # Username rules: English letters/digits/underscore, no spaces
        for bad in ("", "ab", "has space", "1starts", "عربي", "x" * 31, "semi;colon", None, 5):
            res = client.post("/api/trial/signup", json=_payload(bad))
            assert res.status_code == 422 and res.get_json()["field"] == "username", (bad, res.data)
        print("PASS: Invalid usernames are rejected.")

        # Other validation
        res = client.post("/api/trial/signup", json=_payload("okname", name="A"))
        assert res.status_code == 422 and res.get_json()["field"] == "name"
        res = client.post("/api/trial/signup", json=_payload("okname", clinic=""))
        assert res.status_code == 422 and res.get_json()["field"] == "clinic"
        res = client.post("/api/trial/signup", json=_payload("okname", phone="12"))
        assert res.status_code == 422 and res.get_json()["field"] == "phone"
        assert client.post("/api/trial/signup", json={**_payload("okname"), "is_admin": True}).status_code == 400
        print("PASS: Other fields are validated and unknown fields rejected.")

        # Honeypot creates nothing
        before = db.session.scalar(db.select(db.func.count(Clinic.id)))
        res = client.post("/api/trial/signup", json=_payload("botname", website="spam"))
        assert res.status_code == 201 and "data" not in res.get_json()
        assert db.session.scalar(db.select(db.func.count(Clinic.id))) == before
        print("PASS: Honeypot submissions create nothing.")

        # Happy path: credentials follow {username}_{user_id}
        first = client.post("/api/trial/signup", json=_payload(f"Sami{suffix}"))
        assert first.status_code == 201, first.data
        data = first.get_json()["data"]
        user = db.session.scalar(db.select(User).where(User.email == data["email"]))
        assert user is not None and user.role == "head_doctor" and user.is_active
        created_clinics.append(user.clinic_id)
        assert data["email"] == f"sami{suffix}_{user.id}@aerodent.com"
        assert data["password"] == f"sami{suffix}_{user.id}!"
        print("PASS: Credentials follow {username}_{user_id}@aerodent.com / {username}_{user_id}!")

        # Trial clinic setup
        clinic = db.session.get(Clinic, user.clinic_id)
        assert clinic.name == "Smile Clinic" and clinic.subscription_status == "trial"
        remaining = clinic.subscription_expires_at - datetime.now(timezone.utc)
        assert timedelta(days=13, hours=23) < remaining <= timedelta(days=14)
        assert clinic.max_doctors == 3 and clinic.max_secretaries == 3
        req = db.session.scalar(db.select(TrialRequest).where(TrialRequest.created_clinic_id == clinic.id))
        assert req.username == f"sami{suffix}" and req.status == "converted"
        audit = db.session.scalar(
            db.select(AuditLog).where(AuditLog.action == "trial_account_created", AuditLog.clinic_id == clinic.id)
        )
        assert audit is not None and data["password"] not in (audit.details or "")
        print("PASS: Trial clinic has a 14-day expiry, seat limits and an audit trail without secrets.")

        # The signup itself starts a session for the new head doctor
        res = client.get("/api/auth/me")
        assert res.status_code == 200 and res.get_json()["user"]["email"] == data["email"], res.data
        print("PASS: Signing up also signs the new head doctor in.")

        # The generated account can sign in
        res = _client("10.30.0.2").post("/api/auth/login", json={"email": data["email"], "password": data["password"]})
        assert res.status_code == 200 and res.get_json()["user"]["role"] == "head_doctor", res.data
        print("PASS: The generated head doctor can sign in.")

        # User ids are sequential
        second = client.post("/api/trial/signup", json=_payload(f"sami{suffix}"))
        assert second.status_code == 201
        d2 = second.get_json()["data"]
        u2 = db.session.scalar(db.select(User).where(User.email == d2["email"]))
        created_clinics.append(u2.clinic_id)
        assert u2.id > user.id and d2["email"] != data["email"]
        assert d2["email"] == f"sami{suffix}_{u2.id}@aerodent.com"
        print("PASS: Repeating a username yields the next sequential user id.")

        # Per-IP limit (5 per hour; 2 already used above)
        statuses = [client.post("/api/trial/signup", json=_payload(f"rate{i}{suffix}")).status_code for i in range(5)]
        assert statuses[-1] == 429 and statuses.count(201) == 3, statuses
        for row in db.session.scalars(
            db.select(TrialRequest).where(TrialRequest.username.like(f"rate%{suffix}"))
        ).all():
            created_clinics.append(row.created_clinic_id)
        print("PASS: Signups are rate-limited per IP.")
    finally:
        db.session.rollback()
        from backend.routes.admin import purge_clinic_data

        for clinic_id in {cid for cid in created_clinics if cid}:
            purge_clinic_data(clinic_id)
        db.session.query(TrialRequest).filter(TrialRequest.username.like(f"%{suffix}%")).delete(
            synchronize_session=False
        )
        db.session.query(AuthThrottle).delete()
        db.session.commit()
        ctx.pop()

    print("\n==========================================")
    print("ALL TRIAL SIGNUP TESTS PASSED")
    print("==========================================")


if __name__ == "__main__":
    run_trial_signup_tests()
