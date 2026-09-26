import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from datetime import date, time
from uuid import uuid4

from flask import jsonify

from backend.app import app
from backend.auth import (
    authorize_resource,
    login_required,
    require_permission,
    user_has_permission,
    validate_patient_update,
)
from backend.auth.service import hash_password
from backend.extensions import db
from backend.models import Appointment, Clinic, Patient, Treatment, User


TEST_PASSWORD = "Correct Permission Password!"

EXPECTED_PERMISSIONS = {
    "head_doctor": {
        "dashboard.read",
        "patients.read",
        "patients.create",
        "patients.update",
        "patients.delete",
        "odontogram.read",
        "odontogram.update",
        "treatments.read",
        "treatments.create",
        "treatments.update",
        "treatments.delete",
        "treatment_plans.read",
        "treatment_plans.create",
        "treatment_plans.update",
        "treatment_plans.delete",
        "appointments.read",
        "appointments.create",
        "appointments.update",
        "appointments.delete",
        "prescriptions.read",
        "prescriptions.create",
        "prescriptions.update",
        "prescriptions.delete",
        "xrays.read",
        "xrays.create",
        "xrays.update",
        "xrays.delete",
        "invoices.read",
        "invoices.create",
        "invoices.update",
        "invoices.delete",
        "clinic_settings.read",
        "clinic_settings.update",
        "staff.read",
        "staff.create",
        "staff.update",
        "staff.deactivate",
        "staff.delete",
        "inventory.read",
        "inventory.create",
        "inventory.update",
        "inventory.delete",
        "inventory.stock_in",
        "inventory.stock_out",
        "inventory.adjust",
        "inventory.manage_categories",
        "inventory.manage_suppliers",
    },
    "doctor": {
        "dashboard.read",
        "patients.read",
        "patients.create",
        "patients.update",
        "patients.delete",
        "odontogram.read",
        "odontogram.update",
        "treatments.read",
        "treatments.create",
        "treatments.update",
        "treatments.delete",
        "treatment_plans.read",
        "treatment_plans.create",
        "treatment_plans.update",
        "treatment_plans.delete",
        "appointments.read",
        "appointments.create",
        "appointments.update",
        "appointments.delete",
        "prescriptions.read",
        "prescriptions.create",
        "prescriptions.update",
        "prescriptions.delete",
        "xrays.read",
        "xrays.create",
        "xrays.update",
        "xrays.delete",
        "invoices.read",
        "invoices.create",
        "invoices.update",
        "clinic_settings.read",
        "inventory.read",
        "inventory.stock_in",
        "inventory.stock_out",
    },
    "secretary": {
        "dashboard.read",
        "patients.read",
        "patients.create",
        "patients.update",
        "odontogram.read",
        "treatments.read",
        "treatment_plans.read",
        "appointments.read",
        "appointments.create",
        "appointments.update",
        "appointments.delete",
        "prescriptions.read",
        "xrays.read",
        "invoices.read",
        "invoices.create",
        "invoices.update",
        "inventory.read",
        "inventory.stock_in",
        "inventory.stock_out",
        "inventory.manage_suppliers",
    },
}


def _probe(permission):
    @require_permission(permission)
    def probe():
        return jsonify({"ok": True})

    return probe


app.add_url_rule(
    "/__permission_test/dashboard",
    endpoint="permission_test_dashboard",
    view_func=login_required(_probe("dashboard.read")),
    methods=["GET"],
)
app.add_url_rule(
    "/__permission_test/patients-delete",
    endpoint="permission_test_patients_delete",
    view_func=login_required(_probe("patients.delete")),
    methods=["GET"],
)
app.add_url_rule(
    "/__permission_test/staff-read",
    endpoint="permission_test_staff_read",
    view_func=login_required(_probe("staff.read")),
    methods=["GET"],
)


def _new_user(clinic_id, name, email, role):
    return User(
        clinic_id=clinic_id,
        name=name,
        email=email,
        password_hash=hash_password(TEST_PASSWORD),
        role=role,
        is_active=True,
    )


def run_permission_tests():
    suffix = uuid4().hex
    emails = {
        role: f"permission-{role}-{suffix}@aerodent.local"
        for role in EXPECTED_PERMISSIONS
    }

    with app.app_context():
        clinic_a = Clinic(
            name=f"Permission Test A {suffix}",
            currency="SYR",
            work_start=time(9, 0),
            work_end=time(18, 0),
            slot_duration=30,
        )
        clinic_b = Clinic(
            name=f"Permission Test B {suffix}",
            currency="SYR",
            work_start=time(9, 0),
            work_end=time(18, 0),
            slot_duration=30,
        )
        db.session.add_all([clinic_a, clinic_b])
        db.session.flush()

        users = {
            role: _new_user(clinic_a.id, role, emails[role], role)
            for role in EXPECTED_PERMISSIONS
        }
        clinic_b_doctor = _new_user(
            clinic_b.id,
            "Clinic B Doctor",
            f"permission-clinic-b-{suffix}@aerodent.local",
            "doctor",
        )
        db.session.add_all([*users.values(), clinic_b_doctor])
        db.session.flush()

        patient_a = Patient(
            clinic_id=clinic_a.id,
            name="Clinic A Patient",
            created_by=users["doctor"].id,
        )
        patient_b = Patient(
            clinic_id=clinic_b.id,
            name="Clinic B Patient",
            created_by=clinic_b_doctor.id,
        )
        db.session.add_all([patient_a, patient_b])
        db.session.flush()

        treatment_a = Treatment(
            clinic_id=clinic_a.id,
            patient_id=patient_a.id,
            doctor_id=users["doctor"].id,
            created_by=users["doctor"].id,
            status="planned",
            fee=0,
            date=date.today(),
        )
        treatment_b = Treatment(
            clinic_id=clinic_b.id,
            patient_id=patient_b.id,
            doctor_id=clinic_b_doctor.id,
            created_by=clinic_b_doctor.id,
            status="planned",
            fee=0,
            date=date.today(),
        )
        appointment_a = Appointment(
            clinic_id=clinic_a.id,
            patient_id=patient_a.id,
            doctor_id=users["doctor"].id,
            date=date.today(),
            start_time=time(9, 0),
            duration=30,
            status="booked",
            created_by=users["secretary"].id,
        )
        appointment_b = Appointment(
            clinic_id=clinic_b.id,
            patient_id=patient_b.id,
            doctor_id=clinic_b_doctor.id,
            date=date.today(),
            start_time=time(9, 0),
            duration=30,
            status="booked",
            created_by=clinic_b_doctor.id,
        )
        db.session.add_all([treatment_a, treatment_b, appointment_a, appointment_b])
        db.session.commit()

        try:
            for role, expected in EXPECTED_PERMISSIONS.items():
                actual = {
                    permission
                    for permission in set().union(*EXPECTED_PERMISSIONS.values())
                    if user_has_permission(users[role], permission)
                }
                assert actual == expected
            assert not user_has_permission(users["doctor"], "staff.read")
            assert not user_has_permission(users["secretary"], "head_doctor.all")
            print("PASS: All three roles match the centralized permission matrix.")

            for field in {
                "name",
                "phone",
                "location",
                "work_study",
                "dob",
                "gender",
            }:
                assert validate_patient_update(users["secretary"], {field: "value"})

            for role in ("doctor", "head_doctor"):
                for field in {"allergies", "medical_flags", "notes"}:
                    assert validate_patient_update(users[role], {field: "value"})

            for field in {"allergies", "medical_flags", "notes"}:
                try:
                    validate_patient_update(users["secretary"], {field: "value"})
                except PermissionError:
                    pass
                else:
                    raise AssertionError(
                        f"Secretary was allowed to update {field}."
                    )
            print("PASS: Patient clinical fields are protected server-side.")

            assert authorize_resource(
                users["doctor"], "treatments.update", treatment_a
            )
            assert not authorize_resource(
                users["doctor"], "treatments.update", treatment_b
            )
            assert authorize_resource(
                users["secretary"], "appointments.update", appointment_a
            )
            assert not authorize_resource(
                users["secretary"], "appointments.update", appointment_b
            )
            print("PASS: Permission checks remain bounded by clinic ownership.")

            with app.test_client() as client:
                assert client.get("/__permission_test/dashboard").status_code == 401

                response = client.post(
                    "/api/auth/login",
                    json={"email": emails["secretary"], "password": TEST_PASSWORD},
                )
                assert response.status_code == 200

                assert client.get("/__permission_test/dashboard").status_code == 200
                assert client.get("/__permission_test/patients-delete").status_code == 403
                assert client.get("/__permission_test/staff-read").status_code == 403
                print("PASS: Decorators return 401 unauthenticated and 403 forbidden.")

                response = client.get(
                    "/__permission_test/patients-delete",
                    query_string={
                        "role": "head_doctor",
                        "clinic_id": clinic_b.id,
                    },
                )
                assert response.status_code == 403
                print("PASS: Client role and clinic parameters cannot elevate access.")
        finally:
            db.session.delete(clinic_a)
            db.session.delete(clinic_b)
            db.session.commit()


if __name__ == "__main__":
    run_permission_tests()
    print()
    print("==========================================")
    print("ALL PERMISSION TESTS PASSED")
    print("==========================================")