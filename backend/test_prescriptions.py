import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from datetime import date, time
from uuid import uuid4

from backend.app import app
from backend.auth.service import hash_password
from backend.extensions import db
from backend.models import (
    Clinic,
    Patient,
    Prescription,
    PrescriptionMedication,
    User,
)


TEST_PASSWORD = "Correct Prescription Password!"


def create_user(clinic_id, role, suffix):
    return User(
        clinic_id=clinic_id,
        name=f"{role} {suffix}",
        email=f"prescription-{role}-{suffix}@aerodent.local",
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


def prescription_payload(patient_id, **overrides):
    payload = {
        "patient_id": patient_id,
        "date": "2026-09-20",
        "notes": "Take after meals.",
        "medications": [
            {
                "name": "Amoxicillin",
                "dosage": "500 mg",
                "frequency": "Three times daily",
                "duration": "7 days",
                "instructions": "After meals",
            }
        ],
    }
    payload.update(overrides)
    return payload


def run_prescription_tests():
    suffix = uuid4().hex

    with app.app_context():
        clinic_a = Clinic(
            name=f"Prescription Test A {suffix}",
            currency="SYR",
            work_start=time(9, 0),
            work_end=time(18, 0),
            slot_duration=30,
        )
        clinic_b = Clinic(
            name=f"Prescription Test B {suffix}",
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
        prescription_b = Prescription(
            clinic_id=clinic_b.id,
            patient_id=patient_b.id,
            doctor_id=doctor_b.id,
            date=date(2026, 9, 20),
            notes="Clinic B prescription",
            created_by=doctor_b.id,
        )
        prescription_b.medications.append(
            PrescriptionMedication(name="Clinic B Medication")
        )
        db.session.add(prescription_b)
        db.session.commit()

        patient_a_id = patient_a.id
        patient_b_id = patient_b.id
        prescription_b_id = prescription_b.id
        clinic_a_id = clinic_a.id

        try:
            with app.test_client() as client:
                for method, url, kwargs in (
                    ("get", "/api/prescriptions", {}),
                    ("post", "/api/prescriptions", {"json": prescription_payload(patient_a_id)}),
                    ("patch", f"/api/prescriptions/{prescription_b_id}", {"json": {"notes": "x"}}),
                    ("delete", f"/api/prescriptions/{prescription_b_id}", {}),
                ):
                    assert getattr(client, method)(url, **kwargs).status_code == 401
                print("PASS: Unauthenticated prescription operations return 401.")

            with app.test_client() as client:
                login(client, secretary_a)
                assert client.get("/api/prescriptions").status_code == 200
                assert client.post(
                    "/api/prescriptions", json=prescription_payload(patient_a_id)
                ).status_code == 403
                assert client.patch(
                    f"/api/prescriptions/{prescription_b_id}",
                    json={"notes": "denied"},
                ).status_code == 403
                print("PASS: Secretary can read prescriptions but cannot write them.")

            with app.test_client() as client:
                login(client, doctor_a)
                response = client.post(
                    "/api/prescriptions",
                    json=prescription_payload(patient_a_id),
                )
                assert response.status_code == 201
                prescription_id = response.json["data"]["id"]
                created = db.session.get(Prescription, prescription_id)
                assert created.clinic_id == clinic_a_id
                assert created.created_by == doctor_a.id
                assert created.doctor_id == doctor_a.id
                assert len(response.json["data"]["medications"]) == 1
                response = client.get("/api/prescriptions")
                assert response.status_code == 200
                assert response.json["meta"]["total"] == 1
                assert "medications" not in response.json["data"][0]
                response = client.get(f"/api/prescriptions/{prescription_id}")
                assert response.status_code == 200
                assert len(response.json["data"]["medications"]) == 1
                print("PASS: Doctor can create and read prescriptions with medications.")

                response = client.get(
                    "/api/prescriptions",
                    query_string={
                        "patient_id": patient_a_id,
                        "doctor_id": doctor_a.id,
                        "date": "2026-09-20",
                        "page": 1,
                        "per_page": 10,
                    },
                )
                assert response.status_code == 200
                assert response.json["meta"]["total"] == 1

                response = client.post(
                    "/api/prescriptions",
                    json=prescription_payload(patient_a_id, doctor_id=head_a.id),
                )
                assert response.status_code == 201
                head_prescription_id = response.json["data"]["id"]
                assert client.patch(
                    f"/api/prescriptions/{head_prescription_id}",
                    json={"notes": "Head update"},
                ).status_code == 200
                assert client.delete(f"/api/prescriptions/{head_prescription_id}").status_code == 204
                print("PASS: Head-doctor assignment and full doctor access work.")

            with app.test_client() as client:
                login(client, doctor_a)
                response = client.patch(
                    f"/api/prescriptions/{prescription_id}",
                    json={
                        "notes": "Updated instructions",
                        "medications": [
                            {"name": "Ibuprofen", "dosage": "400 mg"},
                            {"name": "Chlorhexidine", "frequency": "Twice daily"},
                        ],
                    },
                )
                assert response.status_code == 200
                assert response.json["data"]["notes"] == "Updated instructions"
                assert [
                    item["name"] for item in response.json["data"]["medications"]
                ] == ["Ibuprofen", "Chlorhexidine"]
                assert db.session.scalar(
                    db.select(db.func.count()).select_from(PrescriptionMedication).where(
                        PrescriptionMedication.prescription_id == prescription_id
                    )
                ) == 2
                print("PASS: PATCH replaces medications transactionally and preserves omitted fields.")

            with app.test_client() as client:
                login(client, doctor_a)
                invalid_payloads = [
                    ({"patient_id": patient_a_id, "date": "2026-09-20", "medications": "Amoxicillin"}, 422),
                    ({"patient_id": patient_a_id, "date": "2026-09-20", "medications": []}, 422),
                    ({"patient_id": patient_a_id, "date": "2026-09-20", "medications": [{"name": ""}]}, 422),
                    ({"patient_id": patient_a_id, "date": "2026-09-20", "medications": [{"name": {"bad": "object"}}]}, 422),
                    ({"patient_id": patient_a_id, "date": "bad-date", "medications": [{"name": "Valid"}]}, 422),
                    ({"patient_id": patient_a_id, "date": "2026-09-20", "medications": [{"name": "Valid", "dosage": {}}]}, 422),
                ]
                for payload, expected_status in invalid_payloads:
                    assert client.post("/api/prescriptions", json=payload).status_code == expected_status

                response = client.post(
                    "/api/prescriptions",
                    json=prescription_payload(
                        patient_a_id,
                        notes="Atomic invalid prescription",
                        medications=[
                            {"name": "Valid medication"},
                            {"name": {"invalid": "object"}},
                        ],
                    ),
                )
                assert response.status_code == 422
                assert db.session.scalar(
                    db.select(Prescription).where(
                        Prescription.notes == "Atomic invalid prescription"
                    )
                ) is None
                print("PASS: Invalid medication input is rejected without partial creation.")

                response = client.post(
                    "/api/prescriptions",
                    json={
                        **prescription_payload(patient_a_id),
                        "clinic_id": 999999,
                        "created_by": 999999,
                        "id": 999999,
                    },
                )
                assert response.status_code == 400
                print("PASS: Prescription ownership fields are server controlled.")

                assert client.post(
                    "/api/prescriptions",
                    json=prescription_payload(patient_b_id),
                ).status_code == 404
                assert client.post(
                    "/api/prescriptions",
                    json=prescription_payload(patient_a_id, doctor_id=doctor_b.id),
                ).status_code == 404
                print("PASS: Cross-clinic patients and doctors are rejected.")

            with app.test_client() as client:
                login(client, doctor_a)
                assert client.get(f"/api/prescriptions/{prescription_b_id}").status_code == 404
                assert client.patch(
                    f"/api/prescriptions/{prescription_b_id}",
                    json={"notes": "cross clinic"},
                ).status_code == 404
                assert client.delete(f"/api/prescriptions/{prescription_b_id}").status_code == 404
                assert db.session.get(Prescription, prescription_b_id) is not None
                print("PASS: Cross-clinic prescription access returns 404.")

                assert client.delete(f"/api/prescriptions/{prescription_id}").status_code == 204
                assert db.session.get(Prescription, prescription_id) is None
                assert db.session.scalars(
                    db.select(PrescriptionMedication).where(
                        PrescriptionMedication.prescription_id == prescription_id
                    )
                ).all() == []
                print("PASS: Prescription deletion cascades medications without unrelated deletes.")
        finally:
            db.session.delete(clinic_a)
            db.session.delete(clinic_b)
            db.session.commit()


if __name__ == "__main__":
    run_prescription_tests()
    print()
    print("==========================================")
    print("ALL PRESCRIPTION API TESTS PASSED")
    print("==========================================")
