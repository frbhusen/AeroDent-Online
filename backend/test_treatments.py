import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from datetime import date, time
from decimal import Decimal
from uuid import uuid4

from backend.app import app
from backend.auth.service import hash_password
from backend.extensions import db
from backend.models import Clinic, Invoice, Patient, Treatment, User


TEST_PASSWORD = "Correct Treatment Password!"


def create_user(clinic_id, role, suffix):
    return User(
        clinic_id=clinic_id,
        name=f"{role} {suffix}",
        email=f"treatment-{role}-{suffix}@aerodent.local",
        password_hash=hash_password(TEST_PASSWORD),
        role=role,
        is_active=True,
    )


def login(client, user):
    response = client.post(
        "/api/auth/login",
        json={"email": user.email, "password": TEST_PASSWORD},
    )
    assert response.status_code == 200


def create_patient(clinic_id, created_by, name):
    patient = Patient(clinic_id=clinic_id, created_by=created_by, name=name)
    db.session.add(patient)
    db.session.flush()
    return patient


def create_treatment(clinic_id, patient_id, doctor_id, created_by, description):
    treatment = Treatment(
        clinic_id=clinic_id,
        patient_id=patient_id,
        doctor_id=doctor_id,
        created_by=created_by,
        tooth_number=14,
        status="planned",
        fee=Decimal("100.00"),
        description=description,
        procedure="filling",
        date=date(2026, 9, 20),
    )
    db.session.add(treatment)
    db.session.flush()
    return treatment


def run_treatment_tests():
    suffix = uuid4().hex

    with app.app_context():
        clinic_a = Clinic(
            name=f"Treatment Test A {suffix}",
            currency="SYR",
            work_start=time(9, 0),
            work_end=time(18, 0),
            slot_duration=30,
        )
        clinic_b = Clinic(
            name=f"Treatment Test B {suffix}",
            currency="SYR",
            work_start=time(9, 0),
            work_end=time(18, 0),
            slot_duration=30,
        )
        db.session.add_all([clinic_a, clinic_b])
        db.session.flush()

        doctor_a = create_user(clinic_a.id, "doctor", suffix)
        head_a = create_user(clinic_a.id, "head_doctor", suffix)
        secretary_a = create_user(clinic_a.id, "secretary", suffix)
        doctor_b = create_user(clinic_b.id, "doctor", f"b-{suffix}")
        db.session.add_all([doctor_a, head_a, secretary_a, doctor_b])
        db.session.flush()

        patient_a = create_patient(clinic_a.id, doctor_a.id, "Clinic A Patient")
        patient_b = create_patient(clinic_b.id, doctor_b.id, "Clinic B Patient")
        treatment_a = create_treatment(
            clinic_a.id,
            patient_a.id,
            doctor_a.id,
            doctor_a.id,
            "Clinic A treatment",
        )
        treatment_b = create_treatment(
            clinic_b.id,
            patient_b.id,
            doctor_b.id,
            doctor_b.id,
            "Clinic B treatment",
        )
        for index in range(3):
            create_treatment(
                clinic_a.id,
                patient_a.id,
                doctor_a.id,
                doctor_a.id,
                f"Pagination treatment {index}",
            )
        db.session.commit()

        patient_a_id = patient_a.id
        patient_b_id = patient_b.id
        treatment_a_id = treatment_a.id
        treatment_b_id = treatment_b.id
        clinic_a_id = clinic_a.id

        try:
            with app.test_client() as client:
                assert client.get("/api/treatments").status_code == 401
                print("PASS: Unauthenticated treatment list is rejected.")

            with app.test_client() as client:
                login(client, doctor_a)
                response = client.get("/api/treatments")
                assert response.status_code == 200
                assert response.json["meta"]["total"] == 4
                assert all(
                    item["clinic_id"] == clinic_a_id
                    for item in response.json["data"]
                )
                response = client.get(
                    "/api/treatments",
                    query_string={"page": 2, "per_page": 2},
                )
                assert response.status_code == 200
                assert response.json["meta"] == {
                    "page": 2,
                    "per_page": 2,
                    "total": 4,
                    "pages": 2,
                }
                response = client.get(
                    "/api/treatments",
                    query_string={"patient_id": patient_a_id, "status": "planned"},
                )
                assert response.status_code == 200
                assert response.json["meta"]["total"] == 4
                assert client.get(
                    "/api/treatments", query_string={"status": "invalid"}
                ).status_code == 400
                print("PASS: Treatment list pagination and filters are clinic scoped.")

                assert client.get(f"/api/treatments/{treatment_a_id}").status_code == 200
                assert client.get(f"/api/treatments/{treatment_b_id}").status_code == 404
                print("PASS: Same-clinic treatment reads work and cross-clinic reads return 404.")

            with app.test_client() as client:
                login(client, secretary_a)
                assert client.get("/api/treatments").status_code == 200
                assert client.post(
                    "/api/treatments",
                    json={"patient_id": patient_a_id, "description": "Denied"},
                ).status_code == 403
                assert client.patch(
                    f"/api/treatments/{treatment_a_id}",
                    json={"status": "completed"},
                ).status_code == 403
                assert client.delete(f"/api/treatments/{treatment_a_id}").status_code == 403
                print("PASS: Secretary is read-only for treatments.")

            with app.test_client() as client:
                login(client, doctor_a)
                response = client.post(
                    "/api/treatments",
                    json={
                        "patient_id": patient_a_id,
                        "doctor_id": head_a.id,
                        "tooth_number": 15,
                        "status": "accepted",
                        "fee": "125.50",
                        "description": "Doctor-created treatment",
                        "procedure": "restoration",
                        "date": "2026-09-20",
                    },
                )
                assert response.status_code == 201
                created_id = response.json["data"]["id"]
                created = db.session.get(Treatment, created_id)
                assert created.clinic_id == clinic_a_id
                assert created.created_by == doctor_a.id
                assert created.doctor_id == head_a.id
                assert response.json["data"]["fee"] == "125.50"
                print("PASS: Doctor can create treatments with validated same-clinic doctor assignment.")

                response = client.patch(
                    f"/api/treatments/{created_id}",
                    json={"status": "completed"},
                )
                assert response.status_code == 200
                assert response.json["data"]["status"] == "completed"
                assert response.json["data"]["description"] == "Doctor-created treatment"
                assert response.json["data"]["fee"] == "125.50"
                print("PASS: Treatment PATCH is partial.")

                response = client.patch(
                    f"/api/treatments/{treatment_b_id}",
                    json={"status": "completed"},
                )
                assert response.status_code == 404
                assert db.session.get(Treatment, treatment_b_id).status == "planned"
                assert client.delete(f"/api/treatments/{created_id}").status_code == 204
                print("PASS: Doctor can update and delete own-clinic treatments.")

            with app.test_client() as client:
                login(client, head_a)
                response = client.post(
                    "/api/treatments",
                    json={"patient_id": patient_a_id, "description": "Head treatment"},
                )
                assert response.status_code == 201
                head_treatment_id = response.json["data"]["id"]
                assert client.patch(
                    f"/api/treatments/{head_treatment_id}",
                    json={"fee": 200},
                ).status_code == 200
                assert client.delete(f"/api/treatments/{head_treatment_id}").status_code == 204
                print("PASS: Head doctor can create, update, and delete treatments.")

            with app.test_client() as client:
                login(client, doctor_a)
                invalid_requests = [
                    ({"patient_id": 999999, "description": "Invalid patient"}, 404),
                    ({"patient_id": patient_b_id, "description": "Cross patient"}, 404),
                    ({"patient_id": patient_a_id, "doctor_id": doctor_b.id}, 404),
                    ({"patient_id": patient_a_id, "tooth_number": 0}, 400),
                    ({"patient_id": patient_a_id, "tooth_number": 33}, 400),
                    ({"patient_id": patient_a_id, "status": "unknown"}, 400),
                    ({"patient_id": patient_a_id, "fee": -100}, 422),
                    ({"patient_id": patient_a_id, "date": "not-a-date"}, 422),
                ]
                for payload, expected_status in invalid_requests:
                    response = client.post("/api/treatments", json=payload)
                    assert response.status_code == expected_status
                print("PASS: Patient, doctor, tooth, status, fee, and date validation work.")

                response = client.post(
                    "/api/treatments",
                    json={
                        "patient_id": patient_a_id,
                        "clinic_id": 999999,
                        "created_by": 999999,
                        "description": "Ownership injection",
                    },
                )
                assert response.status_code == 400
                assert db.session.scalar(
                    db.select(Treatment).where(Treatment.description == "Ownership injection")
                ) is None
                print("PASS: Ownership fields cannot be overridden by clients.")

            with app.test_client() as client:
                login(client, doctor_a)
                invoice_treatment = create_treatment(
                    clinic_a.id,
                    patient_a.id,
                    doctor_a.id,
                    doctor_a.id,
                    "Invoice dependency treatment",
                )
                db.session.commit()
                invoice = Invoice(
                    clinic_id=clinic_a.id,
                    patient_id=patient_a.id,
                    treatment_id=invoice_treatment.id,
                    amount=Decimal("100.00"),
                    paid_amount=Decimal("0.00"),
                    discount=Decimal("0.00"),
                    balance=Decimal("100.00"),
                    status="unpaid",
                    created_by=doctor_a.id,
                )
                db.session.add(invoice)
                db.session.commit()
                invoice_treatment_id = invoice_treatment.id

                response = client.delete(f"/api/treatments/{invoice_treatment_id}")
                assert response.status_code == 409
                assert db.session.get(Treatment, invoice_treatment_id) is not None
                assert db.session.get(Invoice, invoice.id) is not None
                print("PASS: Invoice dependencies block treatment deletion safely.")

                assert client.delete(f"/api/treatments/{treatment_b_id}").status_code == 404
                print("PASS: Cross-clinic treatment deletion returns 404.")
        finally:
            db.session.delete(clinic_a)
            db.session.delete(clinic_b)
            db.session.commit()


if __name__ == "__main__":
    run_treatment_tests()
    print()
    print("==========================================")
    print("ALL TREATMENT API TESTS PASSED")
    print("==========================================")
