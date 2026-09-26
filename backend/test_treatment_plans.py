import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from decimal import Decimal
from datetime import time
from uuid import uuid4

from backend.app import app
from backend.auth.service import hash_password
from backend.extensions import db
from backend.models import Clinic, Patient, TreatmentPlan, User


TEST_PASSWORD = "Correct Treatment Plan Password!"


def create_user(clinic_id, role, suffix):
    return User(
        clinic_id=clinic_id,
        name=f"{role} {suffix}",
        email=f"plan-{role}-{suffix}@aerodent.local",
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


def create_plan(clinic_id, patient_id, doctor_id, created_by, diagnosis):
    plan = TreatmentPlan(
        clinic_id=clinic_id,
        patient_id=patient_id,
        doctor_id=doctor_id,
        created_by=created_by,
        tooth_number=14,
        diagnosis=diagnosis,
        procedure="restoration",
        fee=Decimal("500.00"),
        priority="medium",
        status="planned",
        notes="Plan notes",
    )
    db.session.add(plan)
    db.session.flush()
    return plan


def run_treatment_plan_tests():
    suffix = uuid4().hex

    with app.app_context():
        clinic_a = Clinic(
            name=f"Plan Test A {suffix}",
            currency="SYR",
            work_start=time(9, 0),
            work_end=time(18, 0),
            slot_duration=30,
        )
        clinic_b = Clinic(
            name=f"Plan Test B {suffix}",
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
        plan_a = create_plan(
            clinic_a.id,
            patient_a.id,
            doctor_a.id,
            doctor_a.id,
            "Clinic A diagnosis",
        )
        plan_b = create_plan(
            clinic_b.id,
            patient_b.id,
            doctor_b.id,
            doctor_b.id,
            "Clinic B diagnosis",
        )
        for index in range(3):
            create_plan(
                clinic_a.id,
                patient_a.id,
                doctor_a.id,
                doctor_a.id,
                f"Pagination diagnosis {index}",
            )
        db.session.commit()

        patient_a_id = patient_a.id
        patient_b_id = patient_b.id
        plan_a_id = plan_a.id
        plan_b_id = plan_b.id
        clinic_a_id = clinic_a.id

        try:
            with app.test_client() as client:
                assert client.get("/api/treatment-plans").status_code == 401
                print("PASS: Unauthenticated treatment-plan list is rejected.")

            with app.test_client() as client:
                login(client, doctor_a)
                response = client.get("/api/treatment-plans")
                assert response.status_code == 200
                assert response.json["meta"]["total"] == 4
                assert all(
                    plan["clinic_id"] == clinic_a_id
                    for plan in response.json["data"]
                )

                response = client.get(
                    "/api/treatment-plans",
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
                    "/api/treatment-plans",
                    query_string={
                        "patient_id": patient_a_id,
                        "doctor_id": doctor_a.id,
                        "priority": "medium",
                        "status": "planned",
                    },
                )
                assert response.status_code == 200
                assert response.json["meta"]["total"] == 4
                assert client.get(
                    "/api/treatment-plans",
                    query_string={"priority": "urgent-random"},
                ).status_code == 400
                print("PASS: Treatment-plan pagination and filters are clinic scoped.")

                assert client.get(f"/api/treatment-plans/{plan_a_id}").status_code == 200
                assert client.get(f"/api/treatment-plans/{plan_b_id}").status_code == 404
                print("PASS: Same-clinic reads work and cross-clinic reads return 404.")

            with app.test_client() as client:
                login(client, secretary_a)
                assert client.get("/api/treatment-plans").status_code == 200
                assert client.post(
                    "/api/treatment-plans",
                    json={"patient_id": patient_a_id, "diagnosis": "Denied"},
                ).status_code == 403
                assert client.patch(
                    f"/api/treatment-plans/{plan_a_id}",
                    json={"status": "completed"},
                ).status_code == 403
                assert client.delete(f"/api/treatment-plans/{plan_a_id}").status_code == 403
                print("PASS: Secretary is read-only for treatment plans.")

            with app.test_client() as client:
                login(client, doctor_a)
                response = client.post(
                    "/api/treatment-plans",
                    json={
                        "patient_id": patient_a_id,
                        "doctor_id": head_a.id,
                        "tooth_number": 85,
                        "diagnosis": "Doctor diagnosis",
                        "procedure": "Full restoration",
                        "fee": "1250.50",
                        "priority": "high",
                        "status": "accepted",
                        "notes": "Doctor notes",
                    },
                )
                assert response.status_code == 201
                created_id = response.json["data"]["id"]
                created = db.session.get(TreatmentPlan, created_id)
                assert created.clinic_id == clinic_a_id
                assert created.created_by == doctor_a.id
                assert created.doctor_id == head_a.id
                assert response.json["data"]["fee"] == "1250.50"

                response = client.patch(
                    f"/api/treatment-plans/{created_id}",
                    json={"status": "completed"},
                )
                assert response.status_code == 200
                assert response.json["data"]["status"] == "completed"
                assert response.json["data"]["diagnosis"] == "Doctor diagnosis"
                assert response.json["data"]["fee"] == "1250.50"

                response = client.patch(
                    f"/api/treatment-plans/{plan_b_id}",
                    json={"status": "completed"},
                )
                assert response.status_code == 404
                assert db.session.get(TreatmentPlan, plan_b_id).status == "planned"
                assert client.delete(f"/api/treatment-plans/{plan_b_id}").status_code == 404
                assert client.delete(f"/api/treatment-plans/{created_id}").status_code == 204
                print("PASS: Doctor can create, partially update, and delete plans.")

            with app.test_client() as client:
                login(client, head_a)
                response = client.post(
                    "/api/treatment-plans",
                    json={
                        "patient_id": patient_a_id,
                        "diagnosis": "Head diagnosis",
                        "procedure": "Head procedure",
                    },
                )
                assert response.status_code == 201
                head_plan_id = response.json["data"]["id"]
                assert client.patch(
                    f"/api/treatment-plans/{head_plan_id}",
                    json={"priority": "low"},
                ).status_code == 200
                assert client.delete(f"/api/treatment-plans/{head_plan_id}").status_code == 204
                print("PASS: Head doctor can create, update, and delete plans.")

            with app.test_client() as client:
                login(client, doctor_a)
                invalid_requests = [
                    ({"patient_id": 999999, "diagnosis": "Invalid patient"}, 404),
                    ({"patient_id": patient_b_id, "diagnosis": "Cross patient"}, 404),
                    ({"patient_id": patient_a_id, "doctor_id": doctor_b.id}, 404),
                    ({"patient_id": patient_a_id, "tooth_number": 0}, 400),
                    ({"patient_id": patient_a_id, "tooth_number": 86}, 400),
                    ({"patient_id": patient_a_id, "priority": "urgent-random"}, 400),
                    ({"patient_id": patient_a_id, "status": "unknown"}, 400),
                    ({"patient_id": patient_a_id, "fee": -1}, 422),
                    ({"patient_id": patient_a_id, "diagnosis": {"bad": "data"}}, 422),
                ]
                for payload, expected_status in invalid_requests:
                    response = client.post("/api/treatment-plans", json=payload)
                    assert response.status_code == expected_status

                response = client.post(
                    "/api/treatment-plans",
                    json={
                        "patient_id": patient_a_id,
                        "clinic_id": 999999,
                        "created_by": 999999,
                        "id": 999999,
                        "diagnosis": "Ownership injection",
                    },
                )
                assert response.status_code == 400
                assert db.session.scalar(
                    db.select(TreatmentPlan).where(
                        TreatmentPlan.diagnosis == "Ownership injection"
                    )
                ) is None
                print("PASS: Plan validation and ownership protection work.")
        finally:
            db.session.delete(clinic_a)
            db.session.delete(clinic_b)
            db.session.commit()


if __name__ == "__main__":
    run_treatment_plan_tests()
    print()
    print("==========================================")
    print("ALL TREATMENT PLAN API TESTS PASSED")
    print("==========================================")
