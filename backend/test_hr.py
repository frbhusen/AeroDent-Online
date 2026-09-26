import json
import os
import sys
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.app import app
from backend.extensions import db
from backend.models import Clinic, User, StaffShift, TimeClock, StaffCredential
from backend.auth.service import hash_password


def run_hr_tests():
    with app.app_context():
        # Setup test clinic and users
        clinic = Clinic.query.filter_by(name="HR Test Clinic").first()
        if not clinic:
            clinic = Clinic(
                name="HR Test Clinic",
                currency="USD",
                work_start=time(8, 0),
                work_end=time(18, 0),
                slot_duration=30,
            )
            db.session.add(clinic)
            db.session.commit()

        head_doc = User.query.filter_by(email="hr_head@clinic.local").first()
        if not head_doc:
            head_doc = User(
                clinic_id=clinic.id,
                name="Dr. Head HR",
                email="hr_head@clinic.local",
                password_hash=hash_password("DoctorPass123!"),
                role="head_doctor",
                is_active=True,
            )
            db.session.add(head_doc)
            db.session.commit()

        assistant = User.query.filter_by(email="hr_assistant@clinic.local").first()
        if not assistant:
            assistant = User(
                clinic_id=clinic.id,
                name="Assistant Alice",
                email="hr_assistant@clinic.local",
                password_hash=hash_password("DoctorPass123!"),
                role="secretary",
                is_active=True,
            )
            db.session.add(assistant)
            db.session.commit()

        # Clean up any shifts left over from a previous (possibly interrupted) test run,
        # since this fixture is idempotent by fixed email/name rather than per-run unique.
        StaffShift.query.filter_by(user_id=assistant.id).delete()
        db.session.commit()

        with app.test_client() as client:
            # Login as Head Doctor
            client.post("/api/auth/login", json={"email": "hr_head@clinic.local", "password": "DoctorPass123!"})

            # 1. Staff Scheduling (Shifts)
            shift_res = client.post("/api/hr/shifts", json={
                "user_id": assistant.id,
                "date": "2026-10-01",
                "start_time": "08:30",
                "end_time": "16:30",
                "shift_type": "morning",
                "notes": "Main desk & sterilizer",
            })
            assert shift_res.status_code == 201, f"Shift creation failed: {shift_res.data}"
            shift_id = shift_res.get_json()["data"]["id"]

            list_shifts = client.get("/api/hr/shifts?date=2026-10-01")
            assert list_shifts.status_code == 200
            assert any(s["id"] == shift_id for s in list_shifts.get_json()["data"])

            update_shift = client.patch(f"/api/hr/shifts/{shift_id}", json={"status": "completed"})
            assert update_shift.status_code == 200
            assert update_shift.get_json()["data"]["status"] == "completed"

            # 1b. Updating a shift to invert start/end time is rejected
            inverted_res = client.patch(f"/api/hr/shifts/{shift_id}", json={"start_time": "17:00"})
            assert inverted_res.status_code == 422, f"Expected 422, got {inverted_res.status_code}"

            # 1c. Creating an overlapping shift for the same staff member/date is rejected
            overlap_res = client.post("/api/hr/shifts", json={
                "user_id": assistant.id,
                "date": "2026-10-01",
                "start_time": "09:00",
                "end_time": "10:00",
            })
            assert overlap_res.status_code == 409, f"Expected 409, got {overlap_res.status_code}"

            # 1d. An adjacent (non-overlapping) shift for the same staff member/date is allowed
            adjacent_res = client.post("/api/hr/shifts", json={
                "user_id": assistant.id,
                "date": "2026-10-01",
                "start_time": "16:30",
                "end_time": "18:00",
            })
            assert adjacent_res.status_code == 201, f"Expected 201, got {adjacent_res.status_code}: {adjacent_res.data}"
            adjacent_shift_id = adjacent_res.get_json()["data"]["id"]
            client.delete(f"/api/hr/shifts/{adjacent_shift_id}")
            print("PASS: Shift time-ordering and overlap validation enforced correctly.")

            # 2. Time Clock (Punch in / Punch out)
            status_res = client.get("/api/hr/time-clock/status")
            assert status_res.status_code == 200

            # Clock in
            punch_in = client.post("/api/hr/time-clock/punch", json={"notes": "On time"})
            assert punch_in.status_code in {200, 201}
            assert punch_in.get_json()["action"] == "clock_in"

            # Clock status should be clocked in
            status_check = client.get("/api/hr/time-clock/status")
            assert status_check.get_json()["clocked_in"] is True

            # Clock out
            punch_out = client.post("/api/hr/time-clock/punch", json={"notes": "Heading home"})
            assert punch_out.status_code == 200
            assert punch_out.get_json()["action"] == "clock_out"
            assert punch_out.get_json()["data"]["total_hours"] is not None

            # 3. Staff Credentials / License Expiration Tracking
            today = date.today()
            expiring_soon_date = (today + timedelta(days=15)).isoformat()
            expired_date = (today - timedelta(days=10)).isoformat()
            active_date = (today + timedelta(days=200)).isoformat()

            # Active credential
            cred_active = client.post("/api/hr/credentials", json={
                "user_id": head_doc.id,
                "title": "State Dental Board License",
                "credential_type": "license",
                "credential_number": "DENT-99482",
                "issuing_authority": "Dental Syndicate",
                "expiry_date": active_date,
            })
            assert cred_active.status_code == 201
            assert cred_active.get_json()["data"]["computed_status"] == "active"
            cred_active_id = cred_active.get_json()["data"]["id"]

            # Expiring soon credential
            cred_soon = client.post("/api/hr/credentials", json={
                "user_id": assistant.id,
                "title": "BLS / CPR Certification",
                "credential_type": "certification",
                "expiry_date": expiring_soon_date,
            })
            assert cred_soon.status_code == 201
            assert cred_soon.get_json()["data"]["computed_status"] == "expiring_soon"
            cred_soon_id = cred_soon.get_json()["data"]["id"]

            # Expired credential
            cred_exp = client.post("/api/hr/credentials", json={
                "user_id": assistant.id,
                "title": "Radiation Safety Permit",
                "credential_type": "license",
                "expiry_date": expired_date,
            })
            assert cred_exp.status_code == 201
            assert cred_exp.get_json()["data"]["computed_status"] == "expired"
            cred_exp_id = cred_exp.get_json()["data"]["id"]

            # Summary KPIs check
            summary_res = client.get("/api/hr/credentials/summary")
            assert summary_res.status_code == 200
            summary = summary_res.get_json()["data"]
            assert summary["expiring_soon"] >= 1
            assert summary["expired"] >= 1
            assert summary["needs_attention"] >= 2

            # Clean up
            client.delete(f"/api/hr/shifts/{shift_id}")
            client.delete(f"/api/hr/credentials/{cred_active_id}")
            client.delete(f"/api/hr/credentials/{cred_soon_id}")
            client.delete(f"/api/hr/credentials/{cred_exp_id}")

            print("PASS: HR Staff Scheduling, Time Clock, and Credential Expiration Tracking all verified!")


if __name__ == "__main__":
    run_hr_tests()
