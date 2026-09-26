import json
import os
import sys
from datetime import date, time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.app import app
from backend.extensions import db
from backend.models import Clinic, Patient, User, Waitlist, Appointment
from backend.auth.service import hash_password


def run_waitlist_tests():
    with app.app_context():
        # Setup test clinic and doctor
        clinic = Clinic.query.filter_by(name="Waitlist Test Clinic").first()
        if not clinic:
            clinic = Clinic(
                name="Waitlist Test Clinic",
                currency="USD",
                work_start=time(9, 0),
                work_end=time(18, 0),
                slot_duration=30,
            )
            db.session.add(clinic)
            db.session.commit()

        doctor = User.query.filter_by(email="waitlist_doc@clinic.local").first()
        if not doctor:
            doctor = User(
                clinic_id=clinic.id,
                name="Dr. Waitlist Doctor",
                email="waitlist_doc@clinic.local",
                password_hash=hash_password("DoctorPass123!"),
                role="doctor",
                is_active=True,
            )
            db.session.add(doctor)
            db.session.commit()

        patient = Patient.query.filter_by(clinic_id=clinic.id, name="Waitlist Patient A").first()
        if not patient:
            patient = Patient(
                clinic_id=clinic.id,
                name="Waitlist Patient A",
                phone="1234567890",
                created_by=doctor.id,
            )
            db.session.add(patient)
            db.session.commit()

        with app.test_client() as client:
            # Login
            login_res = client.post(
                "/api/auth/login",
                json={"email": "waitlist_doc@clinic.local", "password": "DoctorPass123!"},
            )
            assert login_res.status_code == 200, f"Login failed: {login_res.data}"

            # Create waitlist entry
            create_res = client.post(
                "/api/waitlist",
                json={
                    "patient_id": patient.id,
                    "procedure": "Crown replacement",
                    "priority": "high",
                    "preferred_time": "morning",
                    "notes": "Prefers morning slots",
                },
            )
            assert create_res.status_code == 201, f"Create waitlist failed: {create_res.data}"
            entry_id = create_res.get_json()["data"]["id"]

            # List waitlist
            list_res = client.get("/api/waitlist")
            assert list_res.status_code == 200
            entries = list_res.get_json()["data"]
            assert any(e["id"] == entry_id for e in entries)

            # Update entry
            update_res = client.patch(
                f"/api/waitlist/{entry_id}",
                json={"priority": "urgent", "notes": "Pain worsening"},
            )
            assert update_res.status_code == 200
            assert update_res.get_json()["data"]["priority"] == "urgent"

            # Auto-fill slot
            autofill_res = client.post(
                f"/api/waitlist/{entry_id}/auto-fill",
                json={
                    "date": "2026-10-15",
                    "start_time": "10:30",
                    "duration": 30,
                },
            )
            assert autofill_res.status_code == 201, f"Autofill failed: {autofill_res.data}"
            res_data = autofill_res.get_json()["data"]
            assert res_data["waitlist"]["status"] == "booked"
            assert res_data["appointment"]["start_time"] == "10:30"

            # Clean up appointment and waitlist
            appt_id = res_data["appointment"]["id"]
            client.delete(f"/api/appointments/{appt_id}")
            client.delete(f"/api/waitlist/{entry_id}")

            print("PASS: Waitlist creation, prioritization, listing, and auto-fill verified.")


if __name__ == "__main__":
    run_waitlist_tests()
