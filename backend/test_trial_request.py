import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from uuid import uuid4

from backend.app import app
from backend.extensions import db
from backend.models import AuditLog, AuthThrottle, TrialRequest


def _client(ip):
    client = app.test_client()
    client.environ_base["REMOTE_ADDR"] = ip
    return client


def run_trial_request_tests():
    suffix = uuid4().hex[:8]
    ctx = app.app_context()
    ctx.push()
    try:
        db.session.query(AuthThrottle).delete()
        db.session.commit()

        # Direct access without going through the button is redirected to sign-in.
        visitor = _client("10.20.0.1")
        res = visitor.get("/request-trial")
        assert res.status_code == 302 and res.headers["Location"].endswith("/"), res.status_code
        res = visitor.get("/trial.html")
        assert res.status_code == 200 and b"onlineLoginForm" in res.data, "trial.html must not bypass the gate"
        res = visitor.post("/api/trial/requests", json={"name": "A B", "phone": "+963 944 000 000", "email": "a@b.co"})
        assert res.status_code == 403
        print("PASS: Request-trial page and API are unreachable without the trial-request flow.")

        # A forged/tampered intent cookie is rejected.
        visitor.set_cookie("aerodent_trial_intent", "forged.value.here")
        assert visitor.get("/request-trial").status_code == 302
        print("PASS: Forged intent cookies are rejected.")

        # Cross-origin sites cannot mint an intent.
        res = visitor.post("/api/trial/intent", json={}, headers={"Origin": "https://evil.example"})
        assert res.status_code == 403
        print("PASS: Cross-origin intent requests are rejected.")

        # Legitimate flow: click -> intent cookie -> page (refresh keeps working).
        user = _client("10.20.0.2")
        res = user.post("/api/trial/intent", json={})
        assert res.status_code == 200 and res.get_json()["redirect"] == "/request-trial"
        cookie = res.headers.get("Set-Cookie", "")
        assert "HttpOnly" in cookie and "SameSite=Strict" in cookie
        for _ in range(2):  # initial load + refresh
            page = user.get("/request-trial")
            assert page.status_code == 200 and b'id="trialForm"' in page.data
            assert page.headers["Cache-Control"] == "no-store"
            assert b"noindex" in page.data
        print("PASS: Clicking the trial button opens the page; refresh keeps it available.")

        # Validation errors name the offending field.
        cases = [
            ({"name": "A", "phone": "+963 944 000 000", "email": "a@b.co"}, "name"),
            ({"name": "Dr. Sami", "phone": "12", "email": "a@b.co"}, "phone"),
            ({"name": "Dr. Sami", "phone": "+963 944 000 000", "email": "not-an-email"}, "email"),
            ({"name": "Dr. Sami", "phone": "+963 944 000 000", "email": "a@b.co", "message": "x" * 1001}, "message"),
            ({"name": "Dr. Sami", "phone": "<script>", "email": "a@b.co"}, "phone"),
        ]
        for payload, field in cases:
            res = user.post("/api/trial/requests", json=payload)
            assert res.status_code == 422 and res.get_json()["field"] == field, (payload, res.data)
        assert user.post("/api/trial/requests", json={"name": ["x"]}).status_code == 422
        assert user.post("/api/trial/requests", json={"name": "x", "is_admin": True}).status_code == 400
        assert user.post("/api/trial/requests", data="not json", content_type="text/plain").status_code == 400
        print("PASS: Invalid and malformed submissions are rejected with field-specific errors.")

        # Honeypot submissions look successful but store nothing.
        before = db.session.scalar(db.select(db.func.count(TrialRequest.id)))
        res = user.post("/api/trial/requests", json={"name": "Bot", "phone": "+1 555 000 0000", "email": "bot@x.io", "website": "spam"})
        assert res.status_code == 201
        assert db.session.scalar(db.select(db.func.count(TrialRequest.id))) == before
        print("PASS: Honeypot field silently drops bot submissions.")

        # Valid submission is stored; the audit entry holds no personal details.
        email = f"clinic.{suffix}@example.com"
        res = user.post("/api/trial/requests", json={
            "name": "Dr. Sami Haddad", "phone": "+963 944 123 456", "email": email,
            "message": "<b>We have 3 chairs</b>", "language": "ar",
        })
        assert res.status_code == 201, res.data
        row = db.session.scalar(db.select(TrialRequest).where(TrialRequest.email == email))
        assert row and row.language == "ar" and row.message == "<b>We have 3 chairs</b>" and row.ip_hash and "10.20" not in row.ip_hash
        audit = db.session.scalar(db.select(AuditLog).where(AuditLog.action == "trial_requested", AuditLog.resource_id == str(row.id)))
        assert audit and email not in (audit.details or "") and "Sami" not in (audit.details or "")
        print("PASS: Valid requests are stored; the audit log records the event without personal data.")

        # Per-IP abuse limit (5 per hour).
        statuses = [user.post("/api/trial/requests", json={
            "name": "Dr. Rami", "phone": "+963 944 123 457", "email": f"r{i}.{suffix}@example.com"}).status_code for i in range(6)]
        assert statuses.count(201) == 4 and statuses[-1] == 429, statuses
        print("PASS: Trial submissions are rate-limited per IP.")
    finally:
        db.session.rollback()
        db.session.query(TrialRequest).filter(TrialRequest.email.like(f"%{suffix}%")).delete(synchronize_session=False)
        db.session.query(AuthThrottle).delete()
        db.session.commit()
        ctx.pop()

    print("\n================================================================")
    print("ALL TRIAL REQUEST TESTS PASSED")
    print("================================================================\n")


if __name__ == "__main__":
    run_trial_request_tests()
