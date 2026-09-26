from datetime import date, time, timedelta
from decimal import Decimal
import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.app import app
from backend.auth.service import hash_password
from backend.extensions import db
from backend.models import (
    Appointment,
    Clinic,
    InventoryCategory,
    InventoryItem,
    InventorySupplier,
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


TEST_PASSWORD = os.getenv("AERODENT_TEST_PASSWORD", "DoctorPassword123!")
SUPER_ADMIN_EMAIL = os.getenv("AERODENT_SUPER_ADMIN_EMAIL", "admin@aerodent.local")
SUPER_ADMIN_PASSWORD = os.getenv("AERODENT_SUPER_ADMIN_PASSWORD", "SuperAdminPassword123!")


def get_or_create_super_admin():
    admin = User.query.filter_by(email=SUPER_ADMIN_EMAIL).first()
    if admin:
        if admin.role != "super_admin":
            admin.role = "super_admin"
        return admin

    admin = User(
        clinic_id=None,
        name="Platform Super Admin",
        email=SUPER_ADMIN_EMAIL,
        password_hash=hash_password(SUPER_ADMIN_PASSWORD),
        role="super_admin",
        is_active=True,
    )
    db.session.add(admin)
    db.session.flush()
    return admin


def get_or_create_user(clinic, name, email, role):
    user = User.query.filter_by(email=email).first()

    if user:
        if user.password_hash == "NOT_SET_YET":
            user.password_hash = hash_password(TEST_PASSWORD)
        return user

    user = User(
        clinic_id=clinic.id,
        name=name,
        email=email,
        password_hash=hash_password(TEST_PASSWORD),
        role=role,
        is_active=True,
    )

    db.session.add(user)
    db.session.flush()

    return user


with app.app_context():
    clinic = Clinic.query.filter_by(
        name="AeroDent Development Clinic"
    ).first()

    if not clinic:
        clinic = Clinic(
            name="AeroDent Development Clinic",
            phone="0000000000",
            address="Development Environment",
            currency="SYR",
            work_start=time(9, 0),
            work_end=time(18, 0),
            slot_duration=30,
        )

        db.session.add(clinic)
        db.session.flush()

    super_admin = get_or_create_super_admin()

    head_doctor = get_or_create_user(
        clinic,
        "Dr. Head Doctor",
        "head@aerodent.local",
        "head_doctor",
    )

    doctor = get_or_create_user(
        clinic,
        "Dr. Test Doctor",
        "doctor@aerodent.local",
        "doctor",
    )

    secretary = get_or_create_user(
        clinic,
        "Test Secretary",
        "secretary@aerodent.local",
        "secretary",
    )

    patient = Patient.query.filter_by(
        clinic_id=clinic.id,
        name="Test Patient",
    ).first()

    if not patient:
        patient = Patient(
            clinic_id=clinic.id,
            name="Test Patient",
            phone="0912345678",
            location="Latakia",
            work_study="Student",
            dob=date(2005, 1, 1),
            gender="male",
            allergies="No known allergies",
            medical_flags="None",
            notes="Development test patient",
            created_by=secretary.id,
        )

        db.session.add(patient)
        db.session.flush()

    odontogram = Odontogram.query.filter_by(
        clinic_id=clinic.id,
        patient_id=patient.id,
        tooth_number=14,
        tooth_mode="permanent",
    ).first()

    if not odontogram:
        odontogram = Odontogram(
            clinic_id=clinic.id,
            patient_id=patient.id,
            tooth_number=14,
            tooth_mode="permanent",
            condition="decay",
            procedure="filling",
            notes="Development test record",
            created_by=doctor.id,
        )

        db.session.add(odontogram)

    treatment = Treatment.query.filter_by(
        clinic_id=clinic.id,
        patient_id=patient.id,
        description="Development test treatment",
    ).first()

    if not treatment:
        treatment = Treatment(
            clinic_id=clinic.id,
            patient_id=patient.id,
            doctor_id=doctor.id,
            created_by=doctor.id,
            tooth_number=14,
            status="completed",
            fee=50000,
            description="Development test treatment",
            procedure="filling",
            date=date.today(),
        )

        db.session.add(treatment)
        db.session.flush()

    plan = TreatmentPlan.query.filter_by(
        clinic_id=clinic.id,
        patient_id=patient.id,
        diagnosis="Development test diagnosis",
    ).first()

    if not plan:
        plan = TreatmentPlan(
            clinic_id=clinic.id,
            patient_id=patient.id,
            doctor_id=doctor.id,
            created_by=doctor.id,
            tooth_number=14,
            diagnosis="Development test diagnosis",
            procedure="filling",
            fee=50000,
            priority="medium",
            status="planned",
            notes="Development test treatment plan",
        )

        db.session.add(plan)

    appointment = Appointment.query.filter_by(
        clinic_id=clinic.id,
        patient_id=patient.id,
        date=date.today(),
        start_time=time(10, 0),
    ).first()

    if not appointment:
        appointment = Appointment(
            clinic_id=clinic.id,
            patient_id=patient.id,
            doctor_id=doctor.id,
            date=date.today(),
            start_time=time(10, 0),
            duration=30,
            status="booked",
            procedure="Follow-up",
            notes="Development test appointment",
            created_by=secretary.id,
        )

        db.session.add(appointment)

    prescription = Prescription.query.filter_by(
        clinic_id=clinic.id,
        patient_id=patient.id,
        date=date.today(),
    ).first()

    if not prescription:
        prescription = Prescription(
            clinic_id=clinic.id,
            patient_id=patient.id,
            doctor_id=doctor.id,
            date=date.today(),
            notes="Development test prescription",
            created_by=doctor.id,
        )

        prescription.medications.append(
            PrescriptionMedication(
                name="Development Test Medication",
                dosage="500 mg",
                frequency="Twice daily",
                duration="5 days",
                instructions="Development test only",
            )
        )

        db.session.add(prescription)

    xray = XRay.query.filter_by(
        clinic_id=clinic.id,
        patient_id=patient.id,
        filename="development-test.webp",
    ).first()

    if xray is None or xray.image is None:
        # A synthetic 16-bit radiograph stored through the same lossless pipeline as uploads.
        from io import BytesIO

        from PIL import Image

        from backend.models import XRayImage
        from backend.services.xray_images import process_upload

        width, height = 480, 320
        radiograph = Image.new("I", (width, height))
        radiograph.putdata([
            int(12000 + 40000 * (1 - abs((x - width / 2) / (width / 2))) * (0.6 + 0.4 * ((y // 40) % 2)))
            for y in range(height) for x in range(width)
        ])
        buffer = BytesIO()
        radiograph.convert("I;16").save(buffer, format="TIFF")
        image_fields = process_upload(buffer.getvalue(), "development-bitewing.tif", "image/tiff")

        if xray is None:
            xray = XRay(
                clinic_id=clinic.id,
                patient_id=patient.id,
                uploaded_by=doctor.id,
                filename="development-test.webp",
                tooth_tag="14",
                type="bitewing",
                date=date.today(),
                time=time(10, 30),
                notes="Synthetic development radiograph",
            )
            db.session.add(xray)
        xray.storage_key = None
        xray.mime_type = image_fields["mime_type"]
        xray.original_mime_type = image_fields["original_mime_type"]
        xray.image = XRayImage(clinic_id=clinic.id, **image_fields)

    invoice = Invoice.query.filter_by(
        clinic_id=clinic.id,
        patient_id=patient.id,
        treatment_id=treatment.id,
    ).first()

    if not invoice:
        invoice = Invoice(
            clinic_id=clinic.id,
            patient_id=patient.id,
            treatment_id=treatment.id,
            amount=50000,
            paid_amount=20000,
            discount=0,
            balance=30000,
            status="partially-paid",
            created_by=secretary.id,
        )

        db.session.add(invoice)

    db.session.commit()

    # Inventory demo data, created through the stock service so the ledger stays consistent.
    if not InventoryItem.query.filter_by(clinic_id=clinic.id).first():
        from backend.services.inventory import receive_stock

        categories = {}
        for name in ("Restorative Materials", "Anesthesia", "PPE", "Disinfection & Sterilization"):
            category = InventoryCategory(clinic_id=clinic.id, name=name, is_active=True)
            db.session.add(category)
            categories[name] = category
        supplier = InventorySupplier(
            clinic_id=clinic.id,
            name="Development Dental Depot",
            contact_person="Sales Desk",
            phone="0110000000",
            is_active=True,
        )
        db.session.add(supplier)
        db.session.flush()

        demo_items = [
            ("Composite A2 syringe", "Restorative Materials", "syringe", 3, "12.50", False, [(8, None, None)]),
            ("Glass ionomer capsule", "Restorative Materials", "capsule", 20, "1.80", False, [(12, None, None)]),
            ("Lidocaine 2% carpule", "Anesthesia", "carpule", 30, "0.90", True, [
                (40, "LD-2402", date.today() + timedelta(days=20)),
                (50, "LD-2410", date.today() + timedelta(days=300)),
            ]),
            ("Nitrile gloves (M)", "PPE", "box", 5, "7.00", False, [(14, None, None)]),
            ("Surface disinfectant 1L", "Disinfection & Sterilization", "bottle", 2, "9.50", True, [
                (3, "SD-001", date.today() - timedelta(days=4)),
            ]),
        ]
        for name, category_name, unit, minimum, cost, tracked, lots in demo_items:
            item = InventoryItem(
                clinic_id=clinic.id,
                name=name,
                category_id=categories[category_name].id,
                supplier_id=supplier.id,
                unit=unit,
                quantity=Decimal("0"),
                minimum_quantity=Decimal(minimum),
                cost_per_unit=Decimal(cost),
                track_batches=tracked,
                is_active=True,
                created_by=head_doctor.id,
            )
            db.session.add(item)
            db.session.flush()
            for quantity, lot, expiry in lots:
                receive_stock(
                    item,
                    quantity=Decimal(quantity),
                    user=head_doctor,
                    movement_type="opening",
                    batch_number=lot,
                    expiry_date=expiry,
                    unit_cost=Decimal(cost),
                    supplier_id=supplier.id,
                    reason="Opening balance",
                )
        db.session.commit()

    print("Development data created successfully.")
    print(f"Clinic ID: {clinic.id}")
    print(f"Head Doctor ID: {head_doctor.id}")
    print(f"Doctor ID: {doctor.id}")
    print(f"Secretary ID: {secretary.id}")
    print(f"Patient ID: {patient.id}")