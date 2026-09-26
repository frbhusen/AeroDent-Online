import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from datetime import time
from uuid import uuid4

from backend.app import app
from backend.auth.service import hash_password
from backend.extensions import db
from backend.models import Clinic, Patient, User


TEST_PASSWORD = "Correct Patients Password!"


def create_user(clinic_id, role, suffix):
    return User(
        clinic_id=clinic_id,
        name=f"{role} {suffix}",
        email=f"patients-{role}-{suffix}@aerodent.local",
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
    patient = Patient(
        clinic_id=clinic_id,
        created_by=created_by,
        name=name,
        phone="0912345678",
        location="Latakia",
        work_study="Student",
        gender="female",
        allergies="No known allergies",
        medical_flags="None",
        notes="Initial notes",
    )
    db.session.add(patient)
    db.session.flush()
    return patient


def run_patient_tests():
    suffix = uuid4().hex

    with app.app_context():
        clinic_a = Clinic(
            name=f"Patients Test A {suffix}",
            currency="SYR",
            work_start=time(9, 0),
            work_end=time(18, 0),
            slot_duration=30,
        )
        clinic_b = Clinic(
            name=f"Patients Test B {suffix}",
            currency="SYR",
            work_start=time(9, 0),
            work_end=time(18, 0),
            slot_duration=30,
        )
        db.session.add_all([clinic_a, clinic_b])
        db.session.flush()

        users = {
            role: create_user(clinic_a.id, role, suffix)
            for role in ("head_doctor", "doctor", "secretary")
        }
        clinic_b_doctor = create_user(clinic_b.id, "doctor", f"b-{suffix}")
        db.session.add_all([*users.values(), clinic_b_doctor])
        db.session.flush()

        patient_a = create_patient(clinic_a.id, users["doctor"].id, "Test Ahmad A")
        patient_b = create_patient(clinic_b.id, clinic_b_doctor.id, "Test Ahmad B")
        for index in range(4):
            create_patient(
                clinic_a.id,
                users["doctor"].id,
                f"Pagination Patient {index}",
            )
        db.session.commit()

        patient_a_id = patient_a.id
        patient_b_id = patient_b.id
        clinic_a_id = clinic_a.id

        try:
            with app.test_client() as client:
                assert client.get("/api/patients").status_code == 401
                print("PASS: Unauthenticated patient list is rejected.")

            with app.test_client() as client:
                login(client, users["doctor"])

                response = client.get("/api/patients")
                assert response.status_code == 200
                assert response.json["meta"]["total"] == 5
                assert all(
                    patient["clinic_id"] == clinic_a_id
                    for patient in response.json["data"]
                )
                print("PASS: Authenticated list is clinic scoped.")

                response = client.get("/api/patients", query_string={"q": "Ahmad"})
                assert response.status_code == 200
                assert len(response.json["data"]) == 1
                assert response.json["data"][0]["id"] == patient_a_id
                print("PASS: Search is clinic scoped and matches patient fields.")

                response = client.get(
                    "/api/patients",
                    query_string={"page": 2, "per_page": 2},
                )
                assert response.status_code == 200
                assert response.json["meta"] == {
                    "page": 2,
                    "per_page": 2,
                    "total": 5,
                    "pages": 3,
                }
                assert len(response.json["data"]) == 2
                response = client.get(
                    "/api/patients",
                    query_string={"per_page": 1000000},
                )
                assert response.status_code == 200
                assert response.json["meta"]["per_page"] == 100
                print("PASS: Pagination metadata and per-page clamping work.")

                response = client.get(f"/api/patients/{patient_a_id}")
                assert response.status_code == 200
                assert response.json["data"]["id"] == patient_a_id

                response = client.get(f"/api/patients/{patient_b_id}")
                assert response.status_code == 404
                print("PASS: Cross-clinic patient reads return 404.")

                response = client.patch(
                    f"/api/patients/{patient_b_id}",
                    json={"name": "Should Remain Clinic B"},
                )
                assert response.status_code == 404
                response = client.delete(f"/api/patients/{patient_b_id}")
                assert response.status_code == 404
                assert db.session.get(Patient, patient_b_id).name == "Test Ahmad B"
                print("PASS: Cross-clinic update and delete are blocked.")

            with app.test_client() as client:
                login(client, users["head_doctor"])
                response = client.post(
                    "/api/patients",
                    json={
                        "name": "Head Created Patient",
                        "phone": "0900000000",
                        "clinic_id": 999999,
                    },
                )
                assert response.status_code == 400
                assert db.session.scalar(
                    db.select(Patient).where(Patient.name == "Head Created Patient")
                ) is None

                response = client.post(
                    "/api/patients",
                    json={"name": "Head Created Patient", "dob": "2000-01-02"},
                )
                assert response.status_code == 201
                head_patient_id = response.json["data"]["id"]
                created = db.session.get(Patient, head_patient_id)
                assert created.clinic_id == clinic_a_id
                assert created.created_by == users["head_doctor"].id

                response = client.patch(
                    f"/api/patients/{head_patient_id}",
                    json={"allergies": "Penicillin", "notes": "Updated"},
                )
                assert response.status_code == 200
                assert response.json["data"]["allergies"] == "Penicillin"
                assert client.delete(f"/api/patients/{head_patient_id}").status_code == 204
                print("PASS: Head doctor can create, update, and delete patients.")

            with app.test_client() as client:
                login(client, users["secretary"])
                response = client.post(
                    "/api/patients",
                    json={"name": "Secretary Created Patient"},
                )
                assert response.status_code == 201
                secretary_patient_id = response.json["data"]["id"]

                response = client.patch(
                    f"/api/patients/{secretary_patient_id}",
                    json={"phone": "0999999999"},
                )
                assert response.status_code == 200

                response = client.patch(
                    f"/api/patients/{secretary_patient_id}",
                    json={"allergies": "Should Be Rejected"},
                )
                assert response.status_code == 403
                assert db.session.get(Patient, secretary_patient_id).allergies is None
                assert client.delete(f"/api/patients/{secretary_patient_id}").status_code == 403
                print("PASS: Secretary can manage administrative fields only.")

            with app.test_client() as client:
                login(client, users["doctor"])
                response = client.post(
                    "/api/patients",
                    json={"name": "Doctor Created Patient"},
                )
                assert response.status_code == 201
                doctor_patient_id = response.json["data"]["id"]
                response = client.patch(
                    f"/api/patients/{doctor_patient_id}",
                    json={"allergies": "Penicillin"},
                )
                assert response.status_code == 200
                assert response.json["data"]["allergies"] == "Penicillin"
                print("PASS: Doctor can create and update clinical fields.")

            with app.test_client() as client:
                login(client, users["doctor"])
                assert client.post("/api/patients", json={"phone": "missing name"}).status_code == 422
                assert client.patch(
                    f"/api/patients/{patient_a_id}",
                    json={"clinic_id": 999999},
                ).status_code == 400
                assert client.patch(
                    f"/api/patients/{patient_a_id}",
                    json={"not_a_patient_field": "value"},
                ).status_code == 400
                print("PASS: Validation rejects missing names and protected fields.")
        finally:
            db.session.delete(clinic_a)
            db.session.delete(clinic_b)
            db.session.commit()


if __name__ == "__main__":
    run_patient_tests()
    print()
    print("==========================================")
    print("ALL PATIENT API TESTS PASSED")
    print("==========================================")
