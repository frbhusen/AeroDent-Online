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
from backend.models import Appointment, Clinic, Patient, User


TEST_PASSWORD = "Correct Appointment Password!"


def create_user(clinic_id, role, suffix):
    return User(
        clinic_id=clinic_id,
        name=f"{role} {suffix}",
        email=f"appointment-{role}-{suffix}@aerodent.local",
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


def create_appointment(
    clinic_id,
    patient_id,
    doctor_id,
    created_by,
    start_time,
    status="booked",
    duration=30,
):
    appointment = Appointment(
        clinic_id=clinic_id,
        patient_id=patient_id,
        doctor_id=doctor_id,
        date=date(2026, 9, 20),
        start_time=start_time,
        duration=duration,
        status=status,
        procedure="Routine appointment",
        notes="Test notes",
        created_by=created_by,
    )
    db.session.add(appointment)
    db.session.flush()
    return appointment


def appointment_payload(patient_id, **overrides):
    payload = {
        "patient_id": patient_id,
        "date": "2026-09-20",
        "start_time": "11:00",
        "duration": 30,
        "status": "booked",
        "procedure": "Routine appointment",
        "notes": "Test notes",
    }
    payload.update(overrides)
    return payload


def run_appointment_tests():
    suffix = uuid4().hex

    with app.app_context():
        clinic_a = Clinic(
            name=f"Appointment Test A {suffix}",
            currency="SYR",
            work_start=time(9, 0),
            work_end=time(18, 0),
            slot_duration=30,
        )
        clinic_b = Clinic(
            name=f"Appointment Test B {suffix}",
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
        base = create_appointment(
            clinic_a.id,
            patient_a.id,
            doctor_a.id,
            doctor_a.id,
            time(10, 0),
        )
        clinic_b_appointment = create_appointment(
            clinic_b.id,
            patient_b.id,
            doctor_b.id,
            doctor_b.id,
            time(10, 0),
        )
        for hour in (14, 15, 16):
            create_appointment(
                clinic_a.id,
                patient_a.id,
                doctor_a.id,
                doctor_a.id,
                time(hour, 0),
            )
        db.session.commit()

        patient_a_id = patient_a.id
        patient_b_id = patient_b.id
        base_id = base.id
        clinic_b_appointment_id = clinic_b_appointment.id
        clinic_a_id = clinic_a.id

        try:
            with app.test_client() as client:
                assert client.get("/api/appointments").status_code == 401
                print("PASS: Unauthenticated appointment list is rejected.")

            with app.test_client() as client:
                login(client, doctor_a)
                response = client.get("/api/appointments")
                assert response.status_code == 200
                assert response.json["meta"]["total"] == 4
                assert all(
                    item["clinic_id"] == clinic_a_id
                    for item in response.json["data"]
                )
                response = client.get(
                    "/api/appointments",
                    query_string={"date": "2026-09-20", "doctor_id": doctor_a.id},
                )
                assert response.status_code == 200
                assert response.json["meta"]["total"] == 4
                response = client.get(
                    "/api/appointments",
                    query_string={"start_date": "2026-09-20", "end_date": "2026-09-20"},
                )
                assert response.status_code == 200
                assert response.json["meta"]["total"] == 4
                response = client.get(
                    "/api/appointments",
                    query_string={"page": 2, "per_page": 2},
                )
                assert response.status_code == 200
                assert response.json["meta"] == {
                    "page": 2,
                    "per_page": 2,
                    "total": 4,
                    "pages": 2,
                }
                assert client.get(
                    "/api/appointments",
                    query_string={"start_date": "2026-09-21", "end_date": "2026-09-20"},
                ).status_code == 400
                print("PASS: Appointment agenda filters and pagination are clinic scoped.")

                assert client.get(f"/api/appointments/{base_id}").status_code == 200
                assert client.get(f"/api/appointments/{clinic_b_appointment_id}").status_code == 404
                print("PASS: Same-clinic reads work and cross-clinic reads return 404.")

            with app.test_client() as client:
                login(client, doctor_a)
                response = client.post(
                    "/api/appointments",
                    json=appointment_payload(patient_a_id, start_time="11:00"),
                )
                assert response.status_code == 201
                doctor_created_id = response.json["data"]["id"]
                doctor_created = db.session.get(Appointment, doctor_created_id)
                assert doctor_created.clinic_id == clinic_a_id
                assert doctor_created.created_by == doctor_a.id
                assert doctor_created.doctor_id == doctor_a.id
                print("PASS: Doctor can create appointments with server ownership.")

            with app.test_client() as client:
                login(client, head_a)
                response = client.post(
                    "/api/appointments",
                    json=appointment_payload(patient_a_id, start_time="12:00"),
                )
                assert response.status_code == 201
                head_created_id = response.json["data"]["id"]
                assert client.patch(
                    f"/api/appointments/{head_created_id}",
                    json={"notes": "Updated by head doctor"},
                ).status_code == 200
                assert client.delete(f"/api/appointments/{head_created_id}").status_code == 204
                print("PASS: Head doctor can create, update, and delete appointments.")

            with app.test_client() as client:
                login(client, secretary_a)
                response = client.get("/api/appointments")
                assert response.status_code == 200
                response = client.post(
                    "/api/appointments",
                    json=appointment_payload(patient_a_id, start_time="13:00"),
                )
                assert response.status_code == 201
                secretary_created_id = response.json["data"]["id"]
                assert response.json["data"]["doctor_id"] is None
                assert client.patch(
                    f"/api/appointments/{secretary_created_id}",
                    json={"status": "completed"},
                ).status_code == 200
                assert client.delete(f"/api/appointments/{secretary_created_id}").status_code == 204
                print("PASS: Secretary has full appointment access.")

            with app.test_client() as client:
                login(client, doctor_a)
                assert client.patch(
                    f"/api/appointments/{clinic_b_appointment_id}",
                    json={"status": "completed"},
                ).status_code == 404
                assert client.delete(f"/api/appointments/{clinic_b_appointment_id}").status_code == 404
                assert db.session.get(Appointment, clinic_b_appointment_id).status == "booked"
                print("PASS: Cross-clinic update and delete are blocked.")

                invalid_requests = [
                    (appointment_payload(patient_b_id, start_time="13:00"), 404),
                    (appointment_payload(patient_a_id, doctor_id=doctor_b.id, start_time="13:00"), 404),
                    (appointment_payload(999999, start_time="13:00"), 404),
                    (appointment_payload(patient_a_id, date="bad-date", start_time="13:00"), 422),
                    (appointment_payload(patient_a_id, start_time="bad-time"), 422),
                    (appointment_payload(patient_a_id, start_time="13:00", duration=0), 422),
                    (appointment_payload(patient_a_id, start_time="13:00", status="invalid"), 400),
                ]
                for payload, expected_status in invalid_requests:
                    assert client.post("/api/appointments", json=payload).status_code == expected_status

                response = client.post(
                    "/api/appointments",
                    json=appointment_payload(
                        patient_a_id,
                        start_time="13:00",
                        clinic_id=999999,
                        created_by=999999,
                        id=999999,
                    ),
                )
                assert response.status_code == 400
                print("PASS: Appointment ownership and input validation work.")

            with app.test_client() as client:
                login(client, doctor_a)
                # Exact, partial, containing, and contained overlaps with base 10:00-10:30.
                for start_time, duration in (
                    ("10:00", 30),
                    ("09:45", 30),
                    ("10:15", 30),
                    ("09:30", 90),
                    ("10:15", 15),
                ):
                    assert client.post(
                        "/api/appointments",
                        json=appointment_payload(
                            patient_a_id,
                            start_time=start_time,
                            duration=duration,
                        ),
                    ).status_code == 409

                assert client.post(
                    "/api/appointments",
                    json=appointment_payload(patient_a_id, start_time="10:30"),
                ).status_code == 201
                assert client.post(
                    "/api/appointments",
                    json=appointment_payload(
                        patient_a_id,
                        doctor_id=head_a.id,
                        start_time="10:00",
                    ),
                ).status_code == 201
                assert client.post(
                    "/api/appointments",
                    json=appointment_payload(
                        patient_a_id,
                        doctor_id=doctor_b.id,
                        start_time="10:00",
                    ),
                ).status_code == 404
                print("PASS: Appointment overlaps are rejected and adjacent times are allowed.")

                cancelled = client.post(
                    "/api/appointments",
                    json=appointment_payload(
                        patient_a_id,
                        start_time="17:00",
                        status="cancelled",
                    ),
                )
                assert cancelled.status_code == 201
                assert client.post(
                    "/api/appointments",
                    json=appointment_payload(patient_a_id, start_time="17:00"),
                ).status_code == 201
                print("PASS: Cancelled appointments do not block active appointments.")

            with app.test_client() as client:
                login(client, doctor_a)
                response = client.post(
                    "/api/appointments",
                    json=appointment_payload(patient_a_id, start_time="08:30"),
                )
                assert response.status_code == 422
                response = client.post(
                    "/api/appointments",
                    json=appointment_payload(patient_a_id, start_time="17:45"),
                )
                assert response.status_code == 422
                assert client.post(
                    "/api/appointments",
                    json=appointment_payload(patient_a_id, start_time="09:00"),
                ).status_code == 201
                assert client.post(
                    "/api/appointments",
                    json=appointment_payload(patient_a_id, start_time="17:30"),
                ).status_code == 201
                print("PASS: Clinic opening and closing hours are enforced server-side.")

            with app.test_client() as client:
                login(client, doctor_a)
                response = client.post(
                    "/api/appointments",
                    json=appointment_payload(patient_a_id, start_time="18:00"),
                )
                assert response.status_code == 422
                movable = client.post(
                    "/api/appointments",
                    json=appointment_payload(patient_a_id, start_time="16:30"),
                )
                assert movable.status_code == 201
                movable_id = movable.json["data"]["id"]
                response = client.patch(
                    f"/api/appointments/{movable_id}",
                    json={"start_time": "16:00"},
                )
                assert response.status_code == 409
                response = client.patch(
                    f"/api/appointments/{movable_id}",
                    json={"start_time": "11:30"},
                )
                assert response.status_code == 200
                assert response.json["data"]["procedure"] == "Routine appointment"
                print("PASS: Rescheduling reruns working-hour and conflict checks.")

                response = client.patch(
                    f"/api/appointments/{base_id}",
                    json={"clinic_id": 999999, "created_by": 999999, "id": 999999},
                )
                assert response.status_code == 400
                assert db.session.get(Appointment, base_id).clinic_id == clinic_a_id
                print("PASS: Appointment identity and ownership remain server controlled.")
        finally:
            db.session.delete(clinic_a)
            db.session.delete(clinic_b)
            db.session.commit()


if __name__ == "__main__":
    run_appointment_tests()
    print()
    print("==========================================")
    print("ALL APPOINTMENT API TESTS PASSED")
    print("==========================================")
