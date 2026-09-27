import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from datetime import date, time, timedelta
from uuid import uuid4

from backend.app import app
from backend.auth.service import hash_password
from backend.extensions import db
from backend.models import Appointment, AuthThrottle, Clinic, Patient, Treatment, User, UserSession
from backend.routes.patients import _months_before


PASSWORD = "Proposed-Features-Pass-1"


def _client(ip, user_agent):
    client = app.test_client()
    client.environ_base["REMOTE_ADDR"] = ip
    client.environ_base["HTTP_USER_AGENT"] = user_agent
    return client


def _login(client, email):
    res = client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    assert res.status_code == 200, res.data
    return client


def run_active_session_tests(head, doctor):
    laptop = _login(_client("203.0.113.25", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128.0 Safari/537.36"), head.email)
    phone = _login(_client("2001:db8:85a3::8a2e:370:7334", "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/128.0 Mobile Safari/537.36 AeroDentAndroid/1.0.0"), head.email)
    other_user = _login(_client("198.51.100.7", "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/605.1.15 Version/17.0 Safari/605.1.15"), doctor.email)

    sessions = laptop.get("/api/auth/sessions").get_json()["sessions"]
    assert len(sessions) == 2, sessions
    current = [s for s in sessions if s["current"]]
    assert len(current) == 1 and current[0]["device"] == {"browser": "Chrome", "os": "Windows", "app": False}
    assert current[0]["ip"] == "203.0.113.x"
    app_session = next(s for s in sessions if not s["current"])
    assert app_session["device"]["app"] is True and app_session["device"]["os"] == "Android"
    assert app_session["ip"] == "2001:0db8:85a3::x"
    assert all("token" not in str(s).lower() for s in sessions)
    print("PASS: A user sees only their own live sessions, with device summary and masked IPs.")

    doctor_session = other_user.get("/api/auth/sessions").get_json()["sessions"][0]["id"]
    foreign = laptop.post(f"/api/auth/sessions/{doctor_session}/revoke")
    missing = laptop.post("/api/auth/sessions/2147483647/revoke")
    assert foreign.status_code == missing.status_code == 404 and foreign.get_json() == missing.get_json()
    assert other_user.get("/api/auth/me").status_code == 200
    print("PASS: Another user's session cannot be revoked (identical to a missing session).")

    assert laptop.post(f"/api/auth/sessions/{current[0]['id']}/revoke").status_code == 400
    res = laptop.post(f"/api/auth/sessions/{app_session['id']}/revoke")
    assert res.status_code == 200, res.data
    assert phone.get("/api/auth/me").status_code == 401
    assert laptop.get("/api/auth/me").status_code == 200
    print("PASS: Revoking one of your other sessions signs that device out immediately.")

    tablet = _login(_client("203.0.113.40", "Mozilla/5.0 (iPad; CPU OS 17_0 like Mac OS X) Safari/604.1"), head.email)
    second_laptop = _login(_client("203.0.113.41", "Mozilla/5.0 (X11; Linux x86_64) Firefox/130.0"), head.email)
    res = laptop.post("/api/auth/sessions/revoke-others")
    assert res.status_code == 200 and res.get_json()["revoked"] == 2, res.data
    assert tablet.get("/api/auth/me").status_code == 401
    assert second_laptop.get("/api/auth/me").status_code == 401
    assert laptop.get("/api/auth/me").status_code == 200
    assert other_user.get("/api/auth/me").status_code == 200
    print("PASS: 'Sign out other sessions' ends every other session of that user only.")

    cross_site = laptop.post("/api/auth/sessions/revoke-others", headers={"Origin": "https://evil.example"})
    assert cross_site.status_code == 403, cross_site.status_code
    assert _client("203.0.113.99", "x").get("/api/auth/sessions").status_code == 401
    print("PASS: Session endpoints require sign-in and reject cross-origin requests.")
    return laptop


def run_recall_tests(clinic, other_clinic, head, other_head, client):
    today = date.today()
    ago = lambda days: today - timedelta(days=days)  # noqa: E731

    def patient(name, clinic_id=clinic.id, created_by=head.id, phone="+963 944 000 000"):
        row = Patient(clinic_id=clinic_id, name=name, phone=phone, created_by=created_by)
        db.session.add(row)
        db.session.flush()
        return row

    def appointment(p, when, status, clinic_id=clinic.id):
        db.session.add(Appointment(clinic_id=clinic_id, patient_id=p.id, date=when, start_time=time(10, 0),
                                   duration=30, status=status))

    def treatment(p, when, status):
        db.session.add(Treatment(clinic_id=clinic.id, patient_id=p.id, date=when, status=status, fee=0))

    overdue_appt = patient("Recall Overdue Appointment")
    appointment(overdue_appt, ago(400), "completed")
    overdue_tx = patient("Recall Overdue Treatment")
    treatment(overdue_tx, ago(250), "completed")
    recent = patient("Recall Recent Visit")
    appointment(recent, ago(400), "completed")
    treatment(recent, ago(20), "completed")
    booked = patient("Recall Already Booked")
    appointment(booked, ago(300), "completed")
    appointment(booked, today + timedelta(days=7), "booked")
    cancelled_future = patient("Recall Cancelled Future")
    appointment(cancelled_future, ago(300), "completed")
    appointment(cancelled_future, today + timedelta(days=7), "cancelled")
    never = patient("Recall Never Visited")
    appointment(never, ago(300), "cancelled")
    treatment(never, ago(300), "planned")
    foreign = patient("Recall Other Clinic", clinic_id=other_clinic.id, created_by=other_head.id)
    appointment(foreign, ago(500), "completed", clinic_id=other_clinic.id)
    db.session.commit()

    res = client.get("/api/patients/recall?months=6")
    assert res.status_code == 200, res.data
    body = res.get_json()
    names = [row["name"] for row in body["data"]]
    assert names == ["Recall Overdue Appointment", "Recall Cancelled Future", "Recall Overdue Treatment"], names
    first = body["data"][0]
    assert first["last_visit"] == ago(400).isoformat() and first["days_since"] == 400
    assert first["phone"] == "+963 944 000 000"
    assert body["meta"]["total"] == 3 and body["meta"]["cutoff"] == _months_before(today, 6).isoformat()
    print("PASS: Recall lists overdue patients (oldest first) and skips recent, booked, never-seen and other clinics' patients.")

    assert [r["name"] for r in client.get("/api/patients/recall?months=12").get_json()["data"]] == ["Recall Overdue Appointment"]
    page = client.get("/api/patients/recall?months=6&per_page=2&page=2").get_json()
    assert [r["name"] for r in page["data"]] == ["Recall Overdue Treatment"] and page["meta"]["pages"] == 2
    for bad in ("0", "37", "-3", "abc", "99999999999"):
        assert client.get(f"/api/patients/recall?months={bad}").status_code == 400, bad
    print("PASS: Recall interval and pagination are validated (1-36 months).")

    other_client = _login(_client("198.51.100.50", "x"), other_head.email)
    assert [r["name"] for r in other_client.get("/api/patients/recall").get_json()["data"]] == ["Recall Other Clinic"]
    print("PASS: Recall results are isolated per clinic.")

    appts = client.get(f"/api/appointments?patient_id={booked.id}").get_json()
    rows = appts.get("data", appts.get("appointments", appts)) if isinstance(appts, dict) else appts
    assert any(row.get("patient_phone") == "+963 944 000 000" for row in rows), appts
    print("PASS: Appointment payloads include the patient's phone for reminders.")


def run_months_before_tests():
    assert _months_before(date(2026, 3, 31), 1) == date(2026, 2, 28)
    assert _months_before(date(2024, 3, 31), 1) == date(2024, 2, 29)
    assert _months_before(date(2026, 1, 15), 6) == date(2025, 7, 15)
    assert _months_before(date(2026, 9, 26), 36) == date(2023, 9, 26)
    print("PASS: Month arithmetic clamps to the end of shorter months.")


def run_proposed_feature_tests():
    suffix = uuid4().hex[:8]
    ctx = app.app_context()
    ctx.push()
    clinic_ids = []
    try:
        db.session.query(AuthThrottle).delete()
        clinic = Clinic(name=f"Proposed A {suffix}", currency="USD")
        other = Clinic(name=f"Proposed B {suffix}", currency="USD")
        db.session.add_all([clinic, other])
        db.session.commit()
        clinic_ids = [clinic.id, other.id]
        head = User(clinic_id=clinic.id, name="Head", email=f"head.{suffix}@proposed.test",
                    password_hash=hash_password(PASSWORD), role="head_doctor", is_active=True)
        doctor = User(clinic_id=clinic.id, name="Doctor", email=f"doctor.{suffix}@proposed.test",
                      password_hash=hash_password(PASSWORD), role="doctor", is_active=True)
        other_head = User(clinic_id=other.id, name="Other Head", email=f"other.{suffix}@proposed.test",
                          password_hash=hash_password(PASSWORD), role="head_doctor", is_active=True)
        db.session.add_all([head, doctor, other_head])
        db.session.commit()

        run_months_before_tests()
        client = run_active_session_tests(head, doctor)
        run_recall_tests(clinic, other, head, other_head, client)
    finally:
        db.session.rollback()
        db.session.query(AuthThrottle).delete()
        from backend.routes.admin import purge_clinic_data
        for clinic_id in clinic_ids:
            purge_clinic_data(clinic_id)
        db.session.commit()
        ctx.pop()

    print("\n================================================================")
    print("ALL PROPOSED FEATURE TESTS PASSED")
    print("================================================================\n")


if __name__ == "__main__":
    run_proposed_feature_tests()
