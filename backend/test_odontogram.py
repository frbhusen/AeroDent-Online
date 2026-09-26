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
from backend.models import Clinic, Odontogram, Patient, User


TEST_PASSWORD = "Correct Odontogram Password!"


def create_user(clinic_id, role, suffix):
    return User(
        clinic_id=clinic_id,
        name=f"{role} {suffix}",
        email=f"odontogram-{role}-{suffix}@aerodent.local",
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


def odontogram_url(patient_id, mode, number):
    return f"/api/patients/{patient_id}/odontogram/{mode}/{number}"


def run_odontogram_tests():
    suffix = uuid4().hex

    with app.app_context():
        clinic_a = Clinic(
            name=f"Odontogram Test A {suffix}",
            currency="SYR",
            work_start=time(9, 0),
            work_end=time(18, 0),
            slot_duration=30,
        )
        clinic_b = Clinic(
            name=f"Odontogram Test B {suffix}",
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
        db.session.commit()

        patient_a_id = patient_a.id
        patient_b_id = patient_b.id

        try:
            with app.test_client() as client:
                assert client.get(f"/api/patients/{patient_a_id}/odontogram").status_code == 401
                assert client.put(
                    odontogram_url(patient_a_id, "permanent", 14),
                    json={"condition": "decay"},
                ).status_code == 401
                assert client.delete(
                    odontogram_url(patient_a_id, "permanent", 14)
                ).status_code == 401
                print("PASS: Unauthenticated odontogram operations return 401.")

            with app.test_client() as client:
                login(client, doctor_a)
                response = client.put(
                    odontogram_url(patient_a_id, "permanent", 14),
                    json={"condition": "decay", "procedure": "filling", "notes": "Initial"},
                )
                assert response.status_code == 201
                record_id = response.json["data"]["id"]
                assert response.json["data"]["created_by"] == doctor_a.id

                response = client.put(
                    odontogram_url(patient_a_id, "permanent", 14),
                    json={"condition": "crown", "notes": "Updated"},
                )
                assert response.status_code == 200
                assert response.json["data"]["id"] == record_id
                assert response.json["data"]["condition"] == "crown"
                assert response.json["data"]["created_by"] == doctor_a.id
                assert db.session.scalar(
                    db.select(db.func.count()).select_from(Odontogram).where(
                        Odontogram.patient_id == patient_a_id,
                        Odontogram.tooth_mode == "permanent",
                        Odontogram.tooth_number == 14,
                    )
                ) == 1
                print("PASS: Doctor create/upsert updates one existing tooth record.")

                response = client.put(
                    odontogram_url(patient_a_id, "primary", 1),
                    json={"condition": "extract", "notes": "Primary tooth"},
                )
                assert response.status_code == 201
                print("PASS: Doctor can create primary and permanent teeth.")

                response = client.get(f"/api/patients/{patient_a_id}/odontogram")
                assert response.status_code == 200
                assert response.json["meta"] == {"patient_id": patient_a_id, "count": 2}

                response = client.get(
                    f"/api/patients/{patient_a_id}/odontogram?mode=primary"
                )
                assert response.status_code == 200
                assert response.json["meta"]["count"] == 1

                assert client.get(
                    f"/api/patients/{patient_a_id}/odontogram?mode=invalid"
                ).status_code == 400
                print("PASS: Doctor can read and filter odontogram records.")

            with app.test_client() as client:
                login(client, head_a)
                response = client.get(f"/api/patients/{patient_a_id}/odontogram")
                assert response.status_code == 200
                response = client.put(
                    odontogram_url(patient_a_id, "permanent", 15),
                    json={"condition": "rct"},
                )
                assert response.status_code == 201
                head_record_id = response.json["data"]["id"]
                assert client.delete(
                    odontogram_url(patient_a_id, "permanent", 15)
                ).status_code == 204
                assert db.session.get(Odontogram, head_record_id) is None
                print("PASS: Head doctor can read, create, and delete odontograms.")

            with app.test_client() as client:
                login(client, secretary_a)
                assert client.get(f"/api/patients/{patient_a_id}/odontogram").status_code == 200
                assert client.put(
                    odontogram_url(patient_a_id, "permanent", 16),
                    json={"condition": "decay"},
                ).status_code == 403
                assert client.delete(
                    odontogram_url(patient_a_id, "permanent", 14)
                ).status_code == 403
                print("PASS: Secretary has read-only odontogram access.")

            with app.test_client() as client:
                login(client, doctor_a)
                for mode, number in (
                    ("unknown", 14),
                    ("permanent", 0),
                    ("permanent", 33),
                    ("primary", 0),
                    ("primary", 21),
                ):
                    response = client.put(
                        odontogram_url(patient_a_id, mode, number),
                        json={"condition": "decay"},
                    )
                    assert response.status_code == 400
                print("PASS: Tooth modes and mode-specific ranges are validated.")

                response = client.put(
                    odontogram_url(patient_a_id, "permanent", 17),
                    json={"clinic_id": 999999, "condition": "decay"},
                )
                assert response.status_code == 400
                response = client.put(
                    odontogram_url(patient_a_id, "permanent", 18),
                    json={"patient_id": 999999, "condition": "decay"},
                )
                assert response.status_code == 400
                response = client.put(
                    odontogram_url(patient_a_id, "permanent", 19),
                    json={"tooth_number": 999, "tooth_mode": "primary", "condition": "decay"},
                )
                assert response.status_code == 400
                assert db.session.scalar(
                    db.select(Odontogram).where(Odontogram.tooth_number == 999)
                ) is None
                print("PASS: Client cannot override clinic, patient, or tooth identity.")

            with app.test_client() as client:
                login(client, doctor_a)
                assert client.get(
                    f"/api/patients/{patient_b_id}/odontogram"
                ).status_code == 404
                assert client.put(
                    odontogram_url(patient_b_id, "permanent", 14),
                    json={"condition": "decay"},
                ).status_code == 404
                assert client.delete(
                    odontogram_url(patient_b_id, "permanent", 14)
                ).status_code == 404
                print("PASS: Cross-clinic read, update, and delete return 404.")

                assert client.delete(
                    odontogram_url(patient_a_id, "permanent", 14)
                ).status_code == 204
                assert db.session.scalar(
                    db.select(Odontogram).where(
                        Odontogram.patient_id == patient_a_id,
                        Odontogram.tooth_mode == "permanent",
                        Odontogram.tooth_number == 14,
                    )
                ) is None
                print("PASS: Doctor delete clears the odontogram record.")
        finally:
            db.session.delete(clinic_a)
            db.session.delete(clinic_b)
            db.session.commit()


if __name__ == "__main__":
    run_odontogram_tests()
    print()
    print("==========================================")
    print("ALL ODONTOGRAM TESTS PASSED")
    print("==========================================")
