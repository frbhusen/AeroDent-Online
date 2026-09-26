import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from datetime import date, time
from decimal import Decimal

from sqlalchemy.exc import IntegrityError

from backend.app import app
from backend.extensions import db
from backend.models import (
    Appointment,
    Clinic,
    Patient,
    Treatment,
    User,
)


def expect_integrity_error(description, callback):
    try:
        with db.session.begin_nested():
            callback()

        raise AssertionError(
            f"FAILED: {description} was accepted by the database."
        )

    except IntegrityError:
        print(f"PASS: {description} was rejected.")


with app.app_context():
    try:
        # ---------------------------------------------------------
        # Create two completely separate clinics.
        # Everything is rolled back at the end of the test.
        # ---------------------------------------------------------

        clinic_a = Clinic(
            name="Isolation Test Clinic A",
            currency="SYR",
            work_start=time(9, 0),
            work_end=time(18, 0),
            slot_duration=30,
        )

        clinic_b = Clinic(
            name="Isolation Test Clinic B",
            currency="SYR",
            work_start=time(9, 0),
            work_end=time(18, 0),
            slot_duration=30,
        )

        db.session.add_all([clinic_a, clinic_b])
        db.session.flush()

        # ---------------------------------------------------------
        # Create staff for both clinics.
        # ---------------------------------------------------------

        doctor_a = User(
            clinic_id=clinic_a.id,
            name="Clinic A Doctor",
            email="isolation-doctor-a@aerodent.local",
            password_hash="TEST_ONLY",
            role="doctor",
            is_active=True,
        )

        doctor_b = User(
            clinic_id=clinic_b.id,
            name="Clinic B Doctor",
            email="isolation-doctor-b@aerodent.local",
            password_hash="TEST_ONLY",
            role="doctor",
            is_active=True,
        )

        db.session.add_all([doctor_a, doctor_b])
        db.session.flush()

        # ---------------------------------------------------------
        # Create one patient per clinic.
        # ---------------------------------------------------------

        patient_a = Patient(
            clinic_id=clinic_a.id,
            name="Clinic A Patient",
            phone="0000000001",
            created_by=doctor_a.id,
        )

        patient_b = Patient(
            clinic_id=clinic_b.id,
            name="Clinic B Patient",
            phone="0000000002",
            created_by=doctor_b.id,
        )

        db.session.add_all([patient_a, patient_b])
        db.session.flush()

        # ---------------------------------------------------------
        # TEST 1
        # A clinic can create a record for its own patient.
        # ---------------------------------------------------------

        valid_treatment = Treatment(
            clinic_id=clinic_a.id,
            patient_id=patient_a.id,
            doctor_id=doctor_a.id,
            created_by=doctor_a.id,
            tooth_number=14,
            status="planned",
            fee=Decimal("1000.00"),
            description="Valid isolation test",
            procedure="filling",
            date=date.today(),
        )

        db.session.add(valid_treatment)
        db.session.flush()

        print("PASS: Clinic A can create a treatment for Clinic A patient.")

        # ---------------------------------------------------------
        # TEST 2
        # Clinic A treatment + Clinic B patient.
        # MUST fail.
        # ---------------------------------------------------------

        expect_integrity_error(
            "Clinic A treatment referencing Clinic B patient",
            lambda: (
                db.session.add(
                    Treatment(
                        clinic_id=clinic_a.id,
                        patient_id=patient_b.id,
                        doctor_id=doctor_a.id,
                        created_by=doctor_a.id,
                        tooth_number=14,
                        status="planned",
                        fee=Decimal("1000.00"),
                        description="INVALID CROSS CLINIC TEST",
                        procedure="filling",
                        date=date.today(),
                    )
                ),
                db.session.flush(),
            ),
        )

        # ---------------------------------------------------------
        # TEST 3
        # Clinic A patient + Clinic B creator.
        # MUST fail.
        # ---------------------------------------------------------

        expect_integrity_error(
            "Clinic A patient created by Clinic B user",
            lambda: (
                db.session.add(
                    Patient(
                        clinic_id=clinic_a.id,
                        name="INVALID CROSS CLINIC PATIENT",
                        phone="0000000003",
                        created_by=doctor_b.id,
                    )
                ),
                db.session.flush(),
            ),
        )

        # ---------------------------------------------------------
        # TEST 4
        # Clinic A appointment + Clinic B doctor.
        # MUST fail.
        # ---------------------------------------------------------

        expect_integrity_error(
            "Clinic A appointment assigned to Clinic B doctor",
            lambda: (
                db.session.add(
                    Appointment(
                        clinic_id=clinic_a.id,
                        patient_id=patient_a.id,
                        doctor_id=doctor_b.id,
                        date=date.today(),
                        start_time=time(11, 0),
                        duration=30,
                        status="booked",
                        procedure="INVALID CROSS CLINIC TEST",
                        notes="Should be rejected",
                        created_by=doctor_a.id,
                    )
                ),
                db.session.flush(),
            ),
        )

        print()
        print("==========================================")
        print("ALL TENANT ISOLATION TESTS PASSED")
        print("==========================================")

    finally:
        # Nothing created by this test remains in the database.
        db.session.rollback()