import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from backend.app import app
from backend.auth.service import hash_password
from backend.extensions import db
from backend.models import AuthThrottle, Clinic, User, UserSession


PASSWORD = "Correct-Horse-Battery-9"


def _client(ip):
    client = app.test_client()
    client.environ_base["REMOTE_ADDR"] = ip
    return client


def _login(client, email, password=PASSWORD):
    return client.post("/api/auth/login", json={"email": email, "password": password})


def _cookie(client):
    cookie = client.get_cookie(app.config["SESSION_COOKIE_NAME"])
    return cookie.value if cookie else None


def run_auth_security_tests():
    suffix = uuid4().hex[:8]
    ctx = app.app_context()
    ctx.push()
    clinic_id = None
    try:
        db.session.query(AuthThrottle).delete()
        clinic = Clinic(name=f"Auth Security {suffix}", currency="USD")
        db.session.add(clinic)
        db.session.commit()
        clinic_id = clinic.id
        head = User(clinic_id=clinic.id, name="Head", email=f"head.{suffix}@auth.test",
                    password_hash=hash_password(PASSWORD), role="head_doctor", is_active=True)
        victim = User(clinic_id=clinic.id, name="Victim", email=f"victim.{suffix}@auth.test",
                      password_hash=hash_password(PASSWORD), role="doctor", is_active=True)
        staff = User(clinic_id=clinic.id, name="Staff", email=f"staff.{suffix}@auth.test",
                     password_hash=hash_password(PASSWORD), role="secretary", is_active=True)
        db.session.add_all([head, victim, staff])
        db.session.commit()

        # 1. Cookie flags -------------------------------------------------------------
        c = _client("10.1.0.1")
        res = _login(c, head.email)
        assert res.status_code == 200, res.data
        set_cookie = res.headers.get("Set-Cookie", "")
        assert "HttpOnly" in set_cookie and "SameSite=Strict" in set_cookie, set_cookie
        assert res.headers.get("Cache-Control") == "no-store, private"
        print("PASS: Session cookie is HttpOnly + SameSite=Strict; auth responses are no-store.")

        # 2. Session fixation: a pre-existing cookie is replaced on login --------------
        before = _cookie(c)
        _login(c, head.email)
        after = _cookie(c)
        assert before and after and before != after
        print("PASS: A new session token is issued on every login (no fixation).")

        # 3. Logout revokes the server-side session; replaying the old cookie fails ----
        stolen = _cookie(c)
        assert c.post("/api/auth/logout").status_code == 200
        replay = _client("10.1.0.1")
        replay.set_cookie(app.config["SESSION_COOKIE_NAME"], stolen)
        assert replay.get("/api/auth/me").status_code == 401
        print("PASS: Logout revokes the session; a copied cookie is rejected afterwards.")

        # 4. Per-account+IP backoff with no user enumeration ----------------------------
        attacker = _client("10.2.0.1")
        codes = [_login(attacker, victim.email, "wrong-password").status_code for _ in range(5)]
        assert codes[:4] == [401, 401, 401, 401] and codes[4] == 429, codes
        locked = _login(attacker, victim.email, PASSWORD)
        assert locked.status_code == 429 and int(locked.headers["Retry-After"]) > 0
        ghost_codes = [_login(attacker, f"nobody.{suffix}@auth.test", "wrong").status_code for _ in range(5)]
        assert ghost_codes == codes, (ghost_codes, codes)
        body_real = _login(_client("10.2.0.9"), victim.email, "wrong").get_json()
        body_ghost = _login(_client("10.2.0.9"), f"nobody.{suffix}@auth.test", "wrong").get_json()
        assert body_real == body_ghost == {"error": "Invalid email or password."}
        print("PASS: Repeated failures back off (429 + Retry-After) identically for real and unknown emails.")

        # 5. The legitimate user on their trusted IP is not locked out by the attacker ---
        home = _client("10.3.0.1")
        db.session.query(AuthThrottle).delete()
        db.session.commit()
        assert _login(home, victim.email).status_code == 200  # establishes trusted origin
        home.post("/api/auth/logout")
        rotating = [_login(_client(f"10.4.0.{i}"), victim.email, "wrong").status_code for i in range(1, 13)]
        assert 429 in rotating, rotating  # account-wide limit caught IP rotation
        assert _login(_client("10.4.0.99"), victim.email, PASSWORD).status_code == 429
        assert _login(home, victim.email).status_code == 200
        print("PASS: IP rotation is stopped per account, while the owner's trusted device still signs in.")

        # 6. Username spraying from one IP is blocked --------------------------------
        sprayer = _client("10.5.0.1")
        spray = [_login(sprayer, f"spray{i}.{suffix}@auth.test", "wrong").status_code for i in range(31)]
        assert spray[-1] == 429 and spray[:29].count(401) == 29, spray
        assert _login(sprayer, staff.email).status_code == 429
        print("PASS: Credential stuffing / username spraying from one IP is throttled.")

        # 7. Locks are temporary --------------------------------------------------------
        db.session.query(AuthThrottle).update({AuthThrottle.locked_until: datetime.now(timezone.utc) - timedelta(seconds=1)})
        db.session.commit()
        assert _login(sprayer, staff.email).status_code == 200
        print("PASS: Locks expire on their own; nothing locks an account permanently.")

        # 8. Password change: brute-force protection and revocation of other sessions ---
        db.session.query(AuthThrottle).delete()
        db.session.commit()
        device_a, device_b = _client("10.6.0.1"), _client("10.6.0.2")
        assert _login(device_a, head.email).status_code == 200
        assert _login(device_b, head.email).status_code == 200
        wrong = [device_a.post("/api/auth/change-password", json={"current_password": "nope", "new_password": "New-Password-123"}).status_code for _ in range(5)]
        assert wrong[:4] == [400] * 4 and wrong[4] == 429, wrong
        db.session.query(AuthThrottle).delete()
        db.session.commit()
        weak = device_a.post("/api/auth/change-password", json={"current_password": PASSWORD, "new_password": "password123"})
        assert weak.status_code == 400
        long_pw = device_a.post("/api/auth/change-password", json={"current_password": PASSWORD, "new_password": "x" * 200})
        assert long_pw.status_code == 400
        ok = device_a.post("/api/auth/change-password", json={"current_password": PASSWORD, "new_password": "New-Password-123"})
        assert ok.status_code == 200, ok.data
        assert device_a.get("/api/auth/me").status_code == 200
        assert device_b.get("/api/auth/me").status_code == 401
        print("PASS: Password change is brute-force protected, enforces policy, and signs out other devices.")

        # 9. Deactivation revokes sessions immediately --------------------------------
        staff_client = _client("10.7.0.1")
        assert _login(staff_client, staff.email).status_code == 200
        res = device_a.patch(f"/api/staff/{staff.id}", json={"is_active": False})
        assert res.status_code == 200, res.data
        assert staff_client.get("/api/auth/me").status_code == 401
        assert db.session.scalar(db.select(db.func.count(UserSession.id)).where(
            UserSession.user_id == staff.id, UserSession.revoked_at.is_(None))) == 0
        print("PASS: Deactivating a user revokes their live sessions.")

        # 10. Idle and absolute expiry --------------------------------------------------
        victim_client = _client("10.3.0.1")
        assert _login(victim_client, victim.email).status_code == 200
        record = db.session.scalar(db.select(UserSession).where(UserSession.user_id == victim.id, UserSession.revoked_at.is_(None)).order_by(UserSession.id.desc()))
        record.last_seen_at = datetime.now(timezone.utc) - app.config["SESSION_IDLE_TIMEOUT"] - timedelta(minutes=1)
        db.session.commit()
        assert victim_client.get("/api/auth/me").status_code == 401
        assert _login(victim_client, victim.email).status_code == 200
        record = db.session.scalar(db.select(UserSession).where(UserSession.user_id == victim.id, UserSession.revoked_at.is_(None)).order_by(UserSession.id.desc()))
        record.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.session.commit()
        assert victim_client.get("/api/auth/me").status_code == 401
        print("PASS: Sessions expire after the idle timeout and at the absolute limit.")

        # 10b. The session-status poll never extends an idle session --------------------
        poller = _client("10.3.0.2")
        assert _login(poller, victim.email).status_code == 200
        record = db.session.scalar(db.select(UserSession).where(UserSession.user_id == victim.id, UserSession.revoked_at.is_(None)).order_by(UserSession.id.desc()))
        stale = datetime.now(timezone.utc) - timedelta(minutes=30)
        record.last_seen_at = stale
        db.session.commit()
        status = poller.get("/api/auth/session-status").get_json()
        assert status["active"] is True and 0 < status["expires_in"] <= app.config["SESSION_IDLE_TIMEOUT"].total_seconds()
        db.session.refresh(record)
        assert abs((record.last_seen_at - stale).total_seconds()) < 1, "status poll must not count as activity"
        record.revoked_at = datetime.now(timezone.utc)
        db.session.commit()
        assert poller.get("/api/auth/session-status").get_json() == {"active": False}
        assert _client("10.3.0.3").get("/api/auth/session-status").get_json() == {"active": False}
        print("PASS: Session-status reports expiry without extending the idle timeout.")

        # 11. Legacy cookie without a server-side session is rejected ------------------
        legacy = _client("10.8.0.1")
        with legacy.session_transaction() as sess:
            sess["user_id"] = head.id
        assert legacy.get("/api/auth/me").status_code == 401
        print("PASS: A signed cookie alone (no server-side session) grants no access.")

        # 12. Self-registration is disabled by default --------------------------------
        res = _client("10.9.0.1").post("/api/auth/register", json={
            "clinic_name": "X", "head_doctor_name": "Y", "email": f"reg.{suffix}@auth.test", "password": "Strong-Pass-123",
        })
        assert res.status_code == 403
        print("PASS: Public self-registration is disabled unless explicitly enabled.")
    finally:
        db.session.rollback()
        db.session.query(AuthThrottle).delete()
        from backend.routes.admin import purge_clinic_data
        if clinic_id:
            purge_clinic_data(clinic_id)
        db.session.commit()
        ctx.pop()

    print("\n================================================================")
    print("ALL AUTH SECURITY TESTS PASSED")
    print("================================================================\n")


if __name__ == "__main__":
    run_auth_security_tests()
