import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import io
from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

from backend.app import app
from backend.auth.service import hash_password
from backend.extensions import db
from backend.models import (
    Appointment,
    Clinic,
    Invoice,
    Odontogram,
    Patient,
    Prescription,
    PrescriptionMedication,
    Treatment,
    TreatmentPlan,
    User,
    XRay,
)

from PIL import Image

def make_test_png():
    out = io.BytesIO()
    Image.new("RGB", (4, 4), "red").save(out, format="PNG")
    return out.getvalue()


def run_e2e_tests():
    suffix = uuid4().hex[:8]
    clinic_a_id = None
    clinic_b_id = None

    ctx = app.app_context()
    ctx.push()
    try:
        # Setup clean test clinics and users
        clinic_a = Clinic(name=f"E2E Clinic A {suffix}", currency="USD")
        clinic_b = Clinic(name=f"E2E Clinic B {suffix}", currency="EUR")
        db.session.add_all([clinic_a, clinic_b])
        db.session.commit()
        clinic_a_id = clinic_a.id
        clinic_b_id = clinic_b.id

        hd_a = User(
            clinic_id=clinic_a.id,
            name="Dr. Head A",
            email=f"head.a.{suffix}@aerodent.test",
            password_hash=hash_password("Password123!"),
            role="head_doctor",
            is_active=True,
        )
        doc_a = User(
            clinic_id=clinic_a.id,
            name="Dr. Staff A",
            email=f"doc.a.{suffix}@aerodent.test",
            password_hash=hash_password("Password123!"),
            role="doctor",
            is_active=True,
        )
        sec_a = User(
            clinic_id=clinic_a.id,
            name="Sec A",
            email=f"sec.a.{suffix}@aerodent.test",
            password_hash=hash_password("Password123!"),
            role="secretary",
            is_active=True,
        )
        hd_b = User(
            clinic_id=clinic_b.id,
            name="Dr. Head B",
            email=f"head.b.{suffix}@aerodent.test",
            password_hash=hash_password("Password123!"),
            role="head_doctor",
            is_active=True,
        )
        db.session.add_all([hd_a, doc_a, sec_a, hd_b])
        db.session.commit()

        client = app.test_client()

        # =====================================================================
        # 1. CLINIC A HEAD DOCTOR FULL WORKFLOW
        # =====================================================================
        # Login
        res = client.post("/api/auth/login", json={"email": f"head.a.{suffix}@aerodent.test", "password": "Password123!"})
        assert res.status_code == 200, f"Head A login failed: {res.data}"
        assert res.json["user"]["role"] == "head_doctor"

        # Create Patient
        res = client.post("/api/patients", json={
            "name": "John Doe",
            "phone": "123456789",
            "location": "Damascus",
            "work_study": "Engineer",
            "dob": "1990-01-01",
            "gender": "Male",
            "allergies": "Penicillin",
            "medical_flags": "Asthma",
            "notes": "Patient prefers morning appointments.",
        })
        assert res.status_code == 201, f"Patient create failed: {res.data}"
        patient_a_id = res.json["data"]["id"]
        assert res.json["data"]["clinic_id"] == clinic_a.id

        # Edit Patient
        res = client.patch(f"/api/patients/{patient_a_id}", json={"phone": "987654321"})
        assert res.status_code == 200
        assert res.json["data"]["phone"] == "987654321"

        # Odontogram Update
        res = client.put(f"/api/patients/{patient_a_id}/odontogram/permanent/14", json={
            "condition": "decay",
            "procedure": "filling",
            "notes": "Mild occlusal caries",
        })
        assert res.status_code in (200, 201), f"Odontogram update failed: {res.data}"
        assert res.json["data"]["condition"] == "decay"

        # Create Treatment
        res = client.post("/api/treatments", json={
            "patient_id": patient_a_id,
            "tooth_number": 14,
            "description": "Composite Restoration",
            "fee": "150.00",
            "status": "planned",
            "date": date.today().isoformat(),
        })
        assert res.status_code == 201, f"Treatment create failed: {res.data}"
        treatment_a_id = res.json["data"]["id"]

        # Create Treatment Plan
        res = client.post("/api/treatment-plans", json={
            "patient_id": patient_a_id,
            "tooth_number": 14,
            "procedure": "Crown placement",
            "diagnosis": "Severe breakdown",
            "priority": "high",
            "status": "planned",
        })
        assert res.status_code == 201, f"Plan create failed: {res.data}"
        plan_a_id = res.json["data"]["id"]

        # Create Appointment
        res = client.post("/api/appointments", json={
            "patient_id": patient_a_id,
            "doctor_id": doc_a.id,
            "date": (date.today() + timedelta(days=2)).isoformat(),
            "start_time": "11:00",
            "duration": 30,
            "procedure": "Crown prep",
            "status": "booked",
        })
        assert res.status_code == 201, f"Appointment create failed: {res.data}"
        appointment_a_id = res.json["data"]["id"]

        # Create Prescription
        res = client.post("/api/prescriptions", json={
            "patient_id": patient_a_id,
            "doctor_id": doc_a.id,
            "date": date.today().isoformat(),
            "medications": [
                {
                    "name": "Amoxicillin",
                    "dosage": "500mg",
                    "frequency": "TID",
                    "duration": "7 days",
                    "instructions": "Take after meals",
                }
            ],
        })
        assert res.status_code == 201, f"Prescription create failed: {res.data}"
        prescription_a_id = res.json["data"]["id"]

        # Upload X-ray
        data = {
            "type": "periapical",
            "tooth_tag": "14",
            "notes": "Pre-op periapical",
            "file": (io.BytesIO(make_test_png()), "tooth14.png"),
        }
        res = client.post(
            f"/api/patients/{patient_a_id}/x-rays",
            data=data,
            content_type="multipart/form-data",
        )
        assert res.status_code == 201, f"X-ray upload failed: {res.data}"
        xray_a_id = res.json["data"]["id"]

        # Create Invoice
        res = client.post("/api/invoices", json={
            "patient_id": patient_a_id,
            "treatment_id": treatment_a_id,
            "amount": "150.00",
            "discount": "10.00",
            "paid_amount": "50.00",
        })
        assert res.status_code == 201, f"Invoice create failed: {res.data}"
        invoice_a_id = res.json["data"]["id"]
        assert res.json["data"]["balance"] == "90.00"
        assert res.json["data"]["status"] == "partially-paid"

        # Update Settings
        res = client.patch("/api/settings", json={"name": "AeroDent Clinic Alpha", "currency": "USD"})
        assert res.status_code == 200
        assert res.json["data"]["name"] == "AeroDent Clinic Alpha"

        # Create Staff
        res = client.post("/api/staff", json={
            "name": "Dr. Assistant",
            "email": f"assistant.{suffix}@aerodent.test",
            "password": "Password123!",
            "role": "doctor",
        })
        assert res.status_code == 201, f"Staff create failed: {res.data}"
        new_staff_id = res.json["data"]["id"]

        # Clinic Export
        res = client.get("/api/clinic/export")
        assert res.status_code == 200
        assert "clinic" in res.json["data"]
        assert len(res.json["data"]["patients"]) >= 1

        print("PASS: Clinic A Head Doctor complete workflow executed.")

        # =====================================================================
        # 2. CLINIC A DOCTOR WORKFLOW & RESTRICTIONS
        # =====================================================================
        res = client.post("/api/auth/login", json={"email": f"doc.a.{suffix}@aerodent.test", "password": "Password123!"})
        assert res.status_code == 200
        assert res.json["user"]["role"] == "doctor"

        # Can read patient & clinical data
        res = client.get(f"/api/patients/{patient_a_id}")
        assert res.status_code == 200

        res = client.get(f"/api/patients/{patient_a_id}/timeline")
        assert res.status_code == 200
        assert len(res.json["data"]) >= 5

        # Prohibited from managing staff
        res = client.get("/api/staff")
        assert res.status_code == 403
        res = client.post("/api/staff", json={"name": "Hacker", "email": "hack@test.com", "password": "pass", "role": "doctor"})
        assert res.status_code == 403

        # Prohibited from updating clinic settings
        res = client.patch("/api/settings", json={"name": "Doctor New Name"})
        assert res.status_code == 403

        # Prohibited from deleting invoice
        res = client.delete(f"/api/invoices/{invoice_a_id}")
        assert res.status_code == 403

        print("PASS: Clinic A Doctor permissions & restrictions verified.")

        # =====================================================================
        # 3. CLINIC A SECRETARY WORKFLOW & RESTRICTIONS
        # =====================================================================
        res = client.post("/api/auth/login", json={"email": f"sec.a.{suffix}@aerodent.test", "password": "Password123!"})
        assert res.status_code == 200
        assert res.json["user"]["role"] == "secretary"

        # Secretary can manage administrative fields of patient
        res = client.patch(f"/api/patients/{patient_a_id}", json={"phone": "111222333"})
        assert res.status_code == 200

        # Secretary cannot touch clinical fields
        res = client.patch(f"/api/patients/{patient_a_id}", json={"allergies": "Sulfa"})
        assert res.status_code == 403

        # Secretary blocked from writing odontogram
        res = client.put(f"/api/patients/{patient_a_id}/odontogram/permanent/15", json={"condition": "decay"})
        assert res.status_code == 403

        # Secretary blocked from writing treatments
        res = client.post("/api/treatments", json={"patient_id": patient_a_id, "description": "Sec treatment", "fee": "100.00"})
        assert res.status_code == 403

        # Secretary blocked from writing treatment plans
        res = client.post("/api/treatment-plans", json={"patient_id": patient_a_id, "procedure": "Sec plan"})
        assert res.status_code == 403

        # Secretary blocked from writing prescriptions
        res = client.post("/api/prescriptions", json={"patient_id": patient_a_id, "doctor_id": doc_a.id, "medications": []})
        assert res.status_code == 403

        # Secretary blocked from uploading X-rays
        res = client.post(f"/api/patients/{patient_a_id}/x-rays", data={"file": (io.BytesIO(make_test_png()), "x.png")}, content_type="multipart/form-data")
        assert res.status_code == 403

        # Secretary has appointments CRUD
        res = client.get("/api/appointments")
        assert res.status_code == 200

        # Secretary has invoice read and update
        res = client.patch(f"/api/invoices/{invoice_a_id}", json={"paid_amount": "140.00"})
        assert res.status_code == 200
        assert res.json["data"]["balance"] == "0.00"
        assert res.json["data"]["status"] == "paid"

        # Secretary blocked from deleting invoice
        res = client.delete(f"/api/invoices/{invoice_a_id}")
        assert res.status_code == 403

        # Secretary blocked from settings and staff
        res = client.get("/api/settings")
        assert res.status_code == 403
        res = client.get("/api/staff")
        assert res.status_code == 403

        print("PASS: Clinic A Secretary permissions & clinical write protections verified.")

        # =====================================================================
        # 4. CROSS-CLINIC ISOLATION (CLINIC B ACCESSING CLINIC A)
        # =====================================================================
        res = client.post("/api/auth/login", json={"email": f"head.b.{suffix}@aerodent.test", "password": "Password123!"})
        assert res.status_code == 200
        assert res.json["user"]["clinic_id"] == clinic_b.id

        # Cross-clinic lookups MUST return 404 (zero information leakage)
        assert client.get(f"/api/patients/{patient_a_id}").status_code == 404
        assert client.patch(f"/api/patients/{patient_a_id}", json={"name": "Hacked"}).status_code == 404
        assert client.delete(f"/api/patients/{patient_a_id}").status_code == 404

        assert client.get(f"/api/patients/{patient_a_id}/odontogram").status_code == 404
        assert client.put(f"/api/patients/{patient_a_id}/odontogram/permanent/14", json={"condition": "clear"}).status_code == 404

        assert client.get(f"/api/treatments/{treatment_a_id}").status_code == 404
        assert client.patch(f"/api/treatments/{treatment_a_id}", json={"description": "Hacked"}).status_code == 404
        assert client.delete(f"/api/treatments/{treatment_a_id}").status_code == 404

        assert client.get(f"/api/treatment-plans/{plan_a_id}").status_code == 404
        assert client.patch(f"/api/treatment-plans/{plan_a_id}", json={"procedure": "Hacked"}).status_code == 404
        assert client.delete(f"/api/treatment-plans/{plan_a_id}").status_code == 404

        assert client.get(f"/api/appointments/{appointment_a_id}").status_code == 404
        assert client.patch(f"/api/appointments/{appointment_a_id}", json={"procedure": "Hacked"}).status_code == 404
        assert client.delete(f"/api/appointments/{appointment_a_id}").status_code == 404

        assert client.get(f"/api/prescriptions/{prescription_a_id}").status_code == 404
        assert client.patch(f"/api/prescriptions/{prescription_a_id}", json={"medications": []}).status_code == 404
        assert client.delete(f"/api/prescriptions/{prescription_a_id}").status_code == 404

        assert client.get(f"/api/x-rays/{xray_a_id}").status_code == 404
        assert client.get(f"/api/x-rays/{xray_a_id}/file").status_code == 404
        assert client.delete(f"/api/x-rays/{xray_a_id}").status_code == 404

        assert client.get(f"/api/invoices/{invoice_a_id}").status_code == 404
        assert client.patch(f"/api/invoices/{invoice_a_id}", json={"paid_amount": "0.00"}).status_code == 404
        assert client.delete(f"/api/invoices/{invoice_a_id}").status_code == 404

        assert client.get(f"/api/patients/{patient_a_id}/timeline").status_code == 404

        # Staff query returns ONLY Clinic B staff
        res = client.get("/api/staff")
        assert res.status_code == 200
        staff_ids = [u["id"] for u in res.json["data"]]
        assert hd_b.id in staff_ids
        assert hd_a.id not in staff_ids
        assert doc_a.id not in staff_ids
        assert sec_a.id not in staff_ids

        # Clinic B export contains zero Clinic A records
        res = client.get("/api/clinic/export")
        assert res.status_code == 200
        assert res.json["data"]["clinic"]["id"] == clinic_b.id
        assert len(res.json["data"]["patients"]) == 0

        print("PASS: Cross-clinic tenant isolation strictly enforced with 404 and zero data leakage.")

    finally:
        from backend.routes.admin import purge_clinic_data
        if clinic_a_id:
            purge_clinic_data(clinic_a_id)
        if clinic_b_id:
            purge_clinic_data(clinic_b_id)
        db.session.commit()
        ctx.pop()

    print("\n================================================================")
    print("ALL MULTI-TENANT E2E INTEGRATION FLOWS PASSED (CLINIC A & B)")
    print("================================================================\n")


if __name__ == "__main__":
    run_e2e_tests()
