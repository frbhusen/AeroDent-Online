import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from datetime import date, time, timedelta
from decimal import Decimal
from uuid import uuid4

from backend.app import app
from backend.services.clinic_backup import load_backup_bytes
from backend.auth.service import hash_password
from backend.extensions import db
from backend.models import (
    Appointment,
    Clinic,
    Invoice,
    Patient,
    Prescription,
    PrescriptionMedication,
    Treatment,
    TreatmentPlan,
    User,
    XRay,
)


TEST_PASSWORD = "Correct Test Password!"


def run_dashboard_settings_staff_timeline_tests():
    suffix = uuid4().hex
    email_a_head = f"head-a-{suffix}@aerodent.local"
    email_a_doc = f"doc-a-{suffix}@aerodent.local"
    email_a_sec = f"sec-a-{suffix}@aerodent.local"
    email_b_head = f"head-b-{suffix}@aerodent.local"

    with app.app_context():
        clinic_a = Clinic(
            name=f"Clinic A {suffix}",
            currency="SYR",
            work_start=time(9, 0),
            work_end=time(18, 0),
            slot_duration=30,
        )
        clinic_b = Clinic(
            name=f"Clinic B {suffix}",
            currency="USD",
            work_start=time(8, 0),
            work_end=time(16, 0),
            slot_duration=15,
        )
        db.session.add_all([clinic_a, clinic_b])
        db.session.flush()

        head_a = User(
            clinic_id=clinic_a.id,
            name="Head Doctor A",
            email=email_a_head,
            password_hash=hash_password(TEST_PASSWORD),
            role="head_doctor",
            is_active=True,
        )
        doc_a = User(
            clinic_id=clinic_a.id,
            name="Doctor A",
            email=email_a_doc,
            password_hash=hash_password(TEST_PASSWORD),
            role="doctor",
            is_active=True,
        )
        sec_a = User(
            clinic_id=clinic_a.id,
            name="Secretary A",
            email=email_a_sec,
            password_hash=hash_password(TEST_PASSWORD),
            role="secretary",
            is_active=True,
        )
        head_b = User(
            clinic_id=clinic_b.id,
            name="Head Doctor B",
            email=email_b_head,
            password_hash=hash_password(TEST_PASSWORD),
            role="head_doctor",
            is_active=True,
        )
        db.session.add_all([head_a, doc_a, sec_a, head_b])
        db.session.flush()

        # Seed data for Clinic A
        patient_a = Patient(
            clinic_id=clinic_a.id,
            created_by=doc_a.id,
            name="Patient A",
            phone="0911111111",
        )
        # Seed data for Clinic B
        patient_b = Patient(
            clinic_id=clinic_b.id,
            created_by=head_b.id,
            name="Patient B",
            phone="0922222222",
        )
        db.session.add_all([patient_a, patient_b])
        db.session.flush()

        # Clinic A appointment & invoice
        today = date.today()
        appt_a = Appointment(
            clinic_id=clinic_a.id,
            patient_id=patient_a.id,
            doctor_id=doc_a.id,
            created_by=doc_a.id,
            date=today,
            start_time=time(10, 0),
            duration=30,
            procedure="Examination",
            status="booked",
        )
        inv_a = Invoice(
            clinic_id=clinic_a.id,
            patient_id=patient_a.id,
            created_by=head_a.id,
            amount=Decimal("100.00"),
            discount=Decimal("10.00"),
            paid_amount=Decimal("40.00"),
            balance=Decimal("50.00"),
            status="partially-paid",
        )
        # Clinic B appointment & invoice
        appt_b = Appointment(
            clinic_id=clinic_b.id,
            patient_id=patient_b.id,
            doctor_id=head_b.id,
            created_by=head_b.id,
            date=today,
            start_time=time(11, 0),
            duration=15,
            procedure="Cleaning",
            status="booked",
        )
        inv_b = Invoice(
            clinic_id=clinic_b.id,
            patient_id=patient_b.id,
            created_by=head_b.id,
            amount=Decimal("500.00"),
            discount=Decimal("0.00"),
            paid_amount=Decimal("0.00"),
            balance=Decimal("500.00"),
            status="unpaid",
        )
        db.session.add_all([appt_a, inv_a, appt_b, inv_b])
        db.session.commit()

        try:
            # 1. Unauthenticated checks
            with app.test_client() as client:
                assert client.get("/api/dashboard").status_code == 401
                assert client.get("/api/settings").status_code == 401
                assert client.get("/api/staff").status_code == 401
                assert client.get("/api/doctors").status_code == 401
                assert client.get(f"/api/patients/{patient_a.id}/timeline").status_code == 401
                print("PASS: Unauthenticated requests rejected for new modules.")

            # 2. Dashboard tests (Clinic A Doctor)
            with app.test_client() as client:
                client.post("/api/auth/login", json={"email": email_a_doc, "password": TEST_PASSWORD})
                res = client.get("/api/dashboard")
                assert res.status_code == 200
                data = res.get_json()["data"]
                assert data["active_patients_count"] == 1
                assert data["upcoming_appointments_count"] == 1
                assert data["outstanding_balance"] == "50.00"  # NOT including Clinic B's 500.00
                assert len(data["upcoming_appointments"]) == 1
                assert data["upcoming_appointments"][0]["patient_name"] == "Patient A"
                print("PASS: Dashboard is accurately scoped to Clinic A.")

            # 3. Settings tests
            # Secretary: no access
            with app.test_client() as client:
                client.post("/api/auth/login", json={"email": email_a_sec, "password": TEST_PASSWORD})
                assert client.get("/api/settings").status_code == 403
                assert client.patch("/api/settings", json={"name": "Hacked"}).status_code == 403
                print("PASS: Secretary cannot access clinic settings.")

            # Doctor: read-only
            with app.test_client() as client:
                client.post("/api/auth/login", json={"email": email_a_doc, "password": TEST_PASSWORD})
                res = client.get("/api/settings")
                assert res.status_code == 200
                assert res.get_json()["data"]["currency"] == "SYR"
                assert client.patch("/api/settings", json={"name": "Doctor New Name"}).status_code == 403
                print("PASS: Doctor has read-only access to clinic settings.")

            # Head doctor: read and update
            with app.test_client() as client:
                client.post("/api/auth/login", json={"email": email_a_head, "password": TEST_PASSWORD})
                res = client.patch(
                    "/api/settings",
                    json={"name": f"Renamed Clinic A {suffix}", "slot_duration": 45},
                )
                assert res.status_code == 200
                assert res.get_json()["data"]["name"] == f"Renamed Clinic A {suffix}"
                assert res.get_json()["data"]["slot_duration"] == 45
                print("PASS: Head doctor can update clinic settings.")

                # Export clinic data
                res_export = client.get("/api/clinic/export")
                assert res_export.status_code == 200
                assert res_export.mimetype == "application/zip"
                _, export_data = load_backup_bytes(res_export.data)
                assert len(export_data["tables"]["patients"]) == 1
                assert export_data["tables"]["patients"][0]["name"] == "Patient A"
                print("PASS: Head doctor can export tenant-isolated clinic data.")

            # 4. Doctors lookup
            with app.test_client() as client:
                client.post("/api/auth/login", json={"email": email_a_sec, "password": TEST_PASSWORD})
                res = client.get("/api/doctors")
                assert res.status_code == 200
                docs = res.get_json()["data"]
                # Must contain Head A and Doc A, but NOT Head B or Sec A
                doc_ids = {d["id"] for d in docs}
                assert head_a.id in doc_ids
                assert doc_a.id in doc_ids
                assert head_b.id not in doc_ids
                assert sec_a.id not in doc_ids
                print("PASS: Doctors list endpoint returns active clinic doctors to all staff.")

            # 5. Staff Management tests
            # Non-head doctor denied
            with app.test_client() as client:
                client.post("/api/auth/login", json={"email": email_a_doc, "password": TEST_PASSWORD})
                assert client.get("/api/staff").status_code == 403
                assert client.post("/api/staff", json={}).status_code == 403
                print("PASS: Doctor denied staff management.")

            # Head doctor management
            with app.test_client() as client:
                client.post("/api/auth/login", json={"email": email_a_head, "password": TEST_PASSWORD})
                # List staff
                res = client.get("/api/staff")
                assert res.status_code == 200
                staff_list = res.get_json()["data"]
                assert len(staff_list) == 3
                assert all("password_hash" not in u for u in staff_list)

                # Create staff
                new_sec_email = f"new-sec-{suffix}@aerodent.local"
                res_create = client.post(
                    "/api/staff",
                    json={
                        "name": "New Assistant",
                        "email": new_sec_email,
                        "password": "StrongPassword123!",
                        "role": "secretary",
                    },
                )
                assert res_create.status_code == 201
                new_id = res_create.get_json()["data"]["id"]

                # Update staff
                res_patch = client.patch(
                    f"/api/staff/{new_id}",
                    json={"name": "Promoted Assistant", "is_active": True},
                )
                assert res_patch.status_code == 200
                assert res_patch.get_json()["data"]["name"] == "Promoted Assistant"

                # Cannot deactivate only head doctor
                res_deact = client.patch(
                    f"/api/staff/{head_a.id}",
                    json={"is_active": False},
                )
                assert res_deact.status_code == 422

                # Cannot delete self
                res_del_self = client.delete(f"/api/staff/{head_a.id}")
                assert res_del_self.status_code == 400

                # Cross-clinic staff access returns 404
                assert client.patch(f"/api/staff/{head_b.id}", json={"name": "Hacked"}).status_code == 404
                assert client.delete(f"/api/staff/{head_b.id}").status_code == 404

                # Delete created staff
                res_del = client.delete(f"/api/staff/{new_id}")
                assert res_del.status_code == 204
                print("PASS: Staff management security, roles, and boundaries enforced.")

            # 6. Timeline tests
            with app.test_client() as client:
                client.post("/api/auth/login", json={"email": email_a_doc, "password": TEST_PASSWORD})
                # Clinic A patient
                res_timeline = client.get(f"/api/patients/{patient_a.id}/timeline")
                assert res_timeline.status_code == 200
                timeline_events = res_timeline.get_json()["data"]
                assert len(timeline_events) >= 1
                assert timeline_events[0]["type"] == "appointment"

                # Cross-clinic patient timeline returns 404
                assert client.get(f"/api/patients/{patient_b.id}/timeline").status_code == 404
                print("PASS: Patient timeline is clinic-isolated and contains server records.")

        finally:
            # Clean up
            db.session.rollback()
            db.session.query(Appointment).filter(Appointment.clinic_id.in_([clinic_a.id, clinic_b.id])).delete(synchronize_session=False)
            db.session.query(Invoice).filter(Invoice.clinic_id.in_([clinic_a.id, clinic_b.id])).delete(synchronize_session=False)
            db.session.query(Patient).filter(Patient.clinic_id.in_([clinic_a.id, clinic_b.id])).delete(synchronize_session=False)
            db.session.query(User).filter(User.clinic_id.in_([clinic_a.id, clinic_b.id])).delete(synchronize_session=False)
            db.session.delete(clinic_a)
            db.session.delete(clinic_b)
            db.session.commit()


if __name__ == "__main__":
    with app.app_context():
        run_dashboard_settings_staff_timeline_tests()
    print()
    print("================================================================")
    print("ALL DASHBOARD, SETTINGS, STAFF & TIMELINE TESTS PASSED")
    print("================================================================")
