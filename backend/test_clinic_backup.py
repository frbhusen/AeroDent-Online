import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import hashlib
import io
import json
import zipfile
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

from PIL import Image

from backend.app import app
from backend.auth.service import hash_password
from backend.extensions import db
from backend.models import (
    Appointment,
    AuditLog,
    AuthThrottle,
    Clinic,
    InventoryBatch,
    InventoryCategory,
    InventoryItem,
    InventoryMovement,
    InventorySupplier,
    Invoice,
    Odontogram,
    Patient,
    Payment,
    Prescription,
    PrescriptionMedication,
    StaffCredential,
    StaffShift,
    TimeClock,
    Treatment,
    TreatmentPlan,
    User,
    Waitlist,
    XRay,
    XRayImage,
)
from backend.services.clinic_backup import DATA_TABLES, count_clinic_rows, load_backup_bytes
from backend.services.xray_images import process_upload


PASSWORD = "Backup-Test-Password-1"


def _client(ip):
    client = app.test_client()
    client.environ_base["REMOTE_ADDR"] = ip
    return client


def _login(client, email):
    res = client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    assert res.status_code == 200, res.data
    return client


def _png(seed):
    image = Image.new("I;16", (40, 30))
    image.putdata([(seed * 997 + i * 37) % 65535 for i in range(40 * 30)])
    buffer = io.BytesIO()
    image.save(buffer, format="TIFF")
    return buffer.getvalue()


def _populate(clinic, head, doctor):
    """One or more rows in every clinic data table."""
    today = date.today()
    patient = Patient(clinic_id=clinic.id, name="Backup Patient", phone="+963 944 111 222", allergies="Penicillin",
                      dob=date(1990, 5, 17), created_by=head.id)
    other = Patient(clinic_id=clinic.id, name="Second Patient", created_by=doctor.id)
    db.session.add_all([patient, other])
    db.session.flush()
    treatment = Treatment(clinic_id=clinic.id, patient_id=patient.id, doctor_id=doctor.id, created_by=head.id,
                          tooth_number=14, status="completed", fee=Decimal("150.50"), procedure="Filling", date=today)
    db.session.add(treatment)
    db.session.flush()
    appointment = Appointment(clinic_id=clinic.id, patient_id=patient.id, doctor_id=doctor.id, created_by=head.id,
                              date=today + timedelta(days=3), start_time=time(10, 30), duration=45, status="booked",
                              procedure="Check-up")
    db.session.add_all([
        appointment,
        TreatmentPlan(clinic_id=clinic.id, patient_id=patient.id, doctor_id=doctor.id, created_by=head.id,
                      tooth_number=36, diagnosis="Caries", procedure="Crown", fee=Decimal("400.00"),
                      priority="high", status="planned"),
        Waitlist(clinic_id=clinic.id, patient_id=other.id, doctor_id=doctor.id, created_by=head.id,
                 preferred_date=today + timedelta(days=10), procedure="Cleaning", priority="urgent", status="waiting"),
        Odontogram(clinic_id=clinic.id, patient_id=patient.id, tooth_number=14, tooth_mode="permanent",
                   condition="filled", created_by=doctor.id),
    ])
    prescription = Prescription(clinic_id=clinic.id, patient_id=patient.id, doctor_id=doctor.id, created_by=doctor.id,
                                date=today, notes="After meals")
    db.session.add(prescription)
    db.session.flush()
    db.session.add(PrescriptionMedication(prescription_id=prescription.id, name="Amoxicillin", dosage="500 mg",
                                          frequency="3x daily", duration="7 days"))
    xray = XRay(clinic_id=clinic.id, patient_id=patient.id, uploaded_by=doctor.id, filename="pano.tiff",
                type="panoramic", date=today, notes="16-bit")
    db.session.add(xray)
    db.session.flush()
    db.session.add(XRayImage(clinic_id=clinic.id, xray_id=xray.id, **process_upload(_png(1), "pano.tiff", "image/tiff")))
    invoice = Invoice(clinic_id=clinic.id, patient_id=patient.id, treatment_id=treatment.id, amount=Decimal("150.50"),
                      paid_amount=Decimal("50.00"), discount=Decimal("0.00"), balance=Decimal("100.50"),
                      status="partially-paid", created_by=head.id)
    db.session.add(invoice)
    db.session.flush()
    db.session.add(Payment(clinic_id=clinic.id, invoice_id=invoice.id, patient_id=patient.id, amount=Decimal("50.00"),
                           payment_method="cash", created_by=head.id))
    category = InventoryCategory(clinic_id=clinic.id, name="Anesthesia")
    supplier = InventorySupplier(clinic_id=clinic.id, name="Dental Supply Co", phone="+963 11 000")
    db.session.add_all([category, supplier])
    db.session.flush()
    item = InventoryItem(clinic_id=clinic.id, name="Articaine", category_id=category.id, supplier_id=supplier.id,
                         quantity=Decimal("40"), minimum_quantity=Decimal("10"), cost_per_unit=Decimal("1.25"),
                         track_batches=True, created_by=head.id)
    db.session.add(item)
    db.session.flush()
    batch = InventoryBatch(clinic_id=clinic.id, item_id=item.id, batch_number="LOT-7", quantity=Decimal("40"),
                           unit_cost=Decimal("1.25"), expiry_date=today + timedelta(days=200), supplier_id=supplier.id)
    db.session.add(batch)
    db.session.flush()
    db.session.add_all([
        InventoryMovement(clinic_id=clinic.id, item_id=item.id, batch_id=batch.id, type="stock_in", quantity=Decimal("42"),
                          quantity_after=Decimal("42"), supplier_id=supplier.id, created_by=head.id),
        InventoryMovement(clinic_id=clinic.id, item_id=item.id, batch_id=batch.id, type="usage", quantity=Decimal("-2"),
                          quantity_after=Decimal("40"), reference_type="patient", reference_id=patient.id,
                          created_by=doctor.id),
        StaffShift(clinic_id=clinic.id, user_id=doctor.id, date=today, start_time=time(9), end_time=time(17),
                   shift_type="regular", status="scheduled", created_by=head.id),
        TimeClock(clinic_id=clinic.id, user_id=doctor.id, clock_in=datetime.now(timezone.utc) - timedelta(hours=3),
                  status="clocked_in"),
        StaffCredential(clinic_id=clinic.id, user_id=doctor.id, title="Dental license", credential_type="license",
                        credential_number="DL-1", expiry_date=today + timedelta(days=365), status="active",
                        created_by=head.id),
    ])
    db.session.commit()
    return patient


def _snapshot(clinic_id):
    """Content that must survive a round trip (IDs differ after import, values must not)."""
    q = lambda stmt: db.session.execute(stmt).all()  # noqa: E731
    return {
        "patients": sorted(q(db.select(Patient.name, Patient.phone, Patient.allergies, Patient.dob).where(Patient.clinic_id == clinic_id))),
        "treatments": sorted(q(db.select(Treatment.procedure, Treatment.fee, Treatment.tooth_number).where(Treatment.clinic_id == clinic_id))),
        "invoices": sorted(q(db.select(Invoice.amount, Invoice.paid_amount, Invoice.balance, Invoice.status).where(Invoice.clinic_id == clinic_id))),
        "medications": sorted(q(db.select(PrescriptionMedication.name, PrescriptionMedication.dosage).join(Prescription).where(Prescription.clinic_id == clinic_id))),
        "xray_bytes": sorted(hashlib.sha256(bytes(d)).hexdigest() for (d,) in q(db.select(XRayImage.data).where(XRayImage.clinic_id == clinic_id))),
        "inventory": sorted(q(db.select(InventoryItem.name, InventoryItem.quantity).where(InventoryItem.clinic_id == clinic_id))),
        "movement_patients": sorted(q(
            db.select(Patient.name).join(InventoryMovement, (InventoryMovement.reference_type == "patient") & (InventoryMovement.reference_id == Patient.id))
            .where(InventoryMovement.clinic_id == clinic_id)
        )),
        "invoice_treatment": sorted(q(db.select(Treatment.procedure).join(Invoice, Invoice.treatment_id == Treatment.id).where(Invoice.clinic_id == clinic_id))),
    }


def _rewrite(raw, mutate):
    """Re-packs an archive after `mutate(files_dict)`, keeping the manifest checksums valid."""
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        files = {name: zf.read(name) for name in zf.namelist()}
    mutate(files)
    manifest = json.loads(files["manifest.json"])
    manifest["files"] = {n: hashlib.sha256(b).hexdigest() for n, b in files.items() if n != "manifest.json"}
    files["manifest.json"] = json.dumps(manifest).encode()
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as zf:
        for name, payload in files.items():
            zf.writestr(name, payload)
    return out.getvalue()


def _import(client, raw, password=PASSWORD, name="backup.zip"):
    return client.post(
        "/api/clinic/import",
        data={"file": (io.BytesIO(raw), name), "password": password},
        content_type="multipart/form-data",
    )


def run_clinic_backup_tests():
    suffix = uuid4().hex[:8]
    ctx = app.app_context()
    ctx.push()
    clinic_ids = []
    try:
        db.session.query(AuthThrottle).delete()

        # 0. Coverage guard: every clinic table is in the backup ---------------------------
        clinic_tables = {t.name for t in db.metadata.sorted_tables if "clinic_id" in t.c}
        missing = clinic_tables - set(DATA_TABLES) - {"users", "audit_logs"}
        assert not missing, f"tables missing from the clinic backup: {missing}"
        print("PASS: Every clinic-scoped table is part of the backup.")

        clinic = Clinic(name=f"Backup A {suffix}", currency="SYP", work_start=time(8), work_end=time(20), slot_duration=15)
        clinic_b = Clinic(name=f"Backup B {suffix}", currency="USD")
        db.session.add_all([clinic, clinic_b])
        db.session.commit()
        clinic_ids = [clinic.id, clinic_b.id]
        mk = lambda c, role, tag: User(clinic_id=c.id, name=f"{role} {tag}", email=f"{tag}.{suffix}@backup.test",  # noqa: E731
                                       password_hash=hash_password(PASSWORD), role=role, is_active=True)
        head, doctor, secretary = mk(clinic, "head_doctor", "head"), mk(clinic, "doctor", "doc"), mk(clinic, "secretary", "sec")
        head_b = mk(clinic_b, "head_doctor", "headb")
        db.session.add_all([head, doctor, secretary, head_b])
        db.session.commit()
        _populate(clinic, head, doctor)
        original = _snapshot(clinic.id)
        original_counts = count_clinic_rows(clinic.id)
        assert all(original_counts[name] >= 1 for name in DATA_TABLES), original_counts

        # 1. Only the head doctor can export or import ---------------------------------------
        for user in (doctor, secretary):
            c = _login(_client("10.80.0.2"), user.email)
            assert c.get("/api/clinic/export").status_code == 403
            assert _import(c, b"PK").status_code == 403
        assert _client("10.80.0.3").get("/api/clinic/export").status_code == 401
        print("PASS: Doctors and secretaries cannot export or import (403); signed-out users get 401.")

        # 2. Export contains everything --------------------------------------------------------
        head_client = _login(_client("10.80.0.1"), head.email)
        res = head_client.get("/api/clinic/export")
        assert res.status_code == 200 and res.mimetype == "application/zip", res.status_code
        assert "attachment" in res.headers["Content-Disposition"] and res.headers["Cache-Control"].startswith("no-store")
        raw = res.data
        manifest, data = load_backup_bytes(raw)
        for name in DATA_TABLES:
            assert len(data["tables"][name]) == original_counts[name], name
        assert {s["email"] for s in data["staff"]} == {head.email, doctor.email, secretary.email}
        assert all("password_hash" not in s for s in data["staff"])
        assert "password_hash" not in json.dumps(data)
        assert data["clinic"]["currency"] == "SYP" and data["clinic"]["slot_duration"] == 15
        assert manifest["counts"]["audit_logs"] == len(data["audit_logs"])
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            for img in data["tables"]["xray_images"]:
                assert hashlib.sha256(zf.read(f"xrays/{img['id']}/data")).hexdigest() == img["sha256"]
        print("PASS: Export holds every table, settings, staff (no password hashes), audit log and exact X-ray bytes.")

        # 3. Restore into the same clinic after changes: back to exactly the exported state ------
        patient = db.session.scalar(db.select(Patient).where(Patient.clinic_id == clinic.id, Patient.name == "Backup Patient"))
        db.session.delete(patient)
        db.session.add(Patient(clinic_id=clinic.id, name="Added After Backup"))
        clinic.currency = "EUR"
        db.session.commit()
        res = _import(head_client, raw)
        assert res.status_code == 200, res.data
        summary = res.get_json()["data"]
        assert summary["unmatched_staff"] == [] and summary["skipped"] == {}
        db.session.expire_all()
        assert _snapshot(clinic.id) == original
        assert count_clinic_rows(clinic.id) == original_counts
        assert db.session.get(Clinic, clinic.id).currency == "SYP"
        restored_xray = db.session.scalar(db.select(XRay).where(XRay.clinic_id == clinic.id))
        assert head_client.get(f"/api/x-rays/{restored_xray.id}/verify").get_json()["data"]["verified"] is True
        shift = db.session.scalar(db.select(StaffShift).where(StaffShift.clinic_id == clinic.id))
        assert shift.user_id == doctor.id
        print("PASS: Import restores the exact exported state (records, links, X-ray bytes, settings, HR).")

        # 4. Audit trail -------------------------------------------------------------------------
        actions = set(db.session.scalars(db.select(AuditLog.action).where(AuditLog.clinic_id == clinic.id)))
        assert {"clinic_data_exported", "clinic_data_imported"} <= actions
        print("PASS: Exports and imports are recorded in the audit log (which import never overwrites).")

        # 5. Import into another clinic: remapped IDs, staff-specific rows skipped, A untouched -----
        before_a = count_clinic_rows(clinic.id)
        b_client = _login(_client("10.80.0.9"), head_b.email)
        res = _import(b_client, raw)
        assert res.status_code == 200, res.data
        summary = res.get_json()["data"]
        assert set(summary["unmatched_staff"]) == {head.email, doctor.email, secretary.email}
        assert summary["skipped"] == {"staff_shifts": 1, "time_clocks": 1, "staff_credentials": 1}
        counts_b = count_clinic_rows(clinic_b.id)
        for name in DATA_TABLES:
            expected = 0 if name in summary["skipped"] else original_counts[name]
            assert counts_b[name] == expected, (name, counts_b[name], expected)
        assert _snapshot(clinic_b.id) == original
        assert count_clinic_rows(clinic.id) == before_a
        creators = set(db.session.scalars(db.select(Patient.created_by).where(Patient.clinic_id == clinic_b.id)))
        assert creators == {head_b.id}
        doctors = set(db.session.scalars(db.select(Treatment.doctor_id).where(Treatment.clinic_id == clinic_b.id)))
        assert doctors == {None}
        print("PASS: Import into another clinic remaps every reference; staff links fall back safely; source untouched.")

        # 5b. An image already damaged in the database does not make the backup unusable ------
        damaged_image = db.session.scalar(db.select(XRayImage).where(XRayImage.clinic_id == clinic_b.id))
        damaged_image.data = bytes(damaged_image.data[:-1]) + bytes([damaged_image.data[-1] ^ 0xFF])
        db.session.commit()
        db.session.query(AuthThrottle).delete()
        db.session.commit()
        raw_b = b_client.get("/api/clinic/export").data
        manifest_b, _ = load_backup_bytes(raw_b)
        assert manifest_b["corrupt_images"] == [damaged_image.id]
        res = _import(b_client, raw_b)
        assert res.status_code == 200, res.data
        restored = db.session.scalar(db.select(XRay).where(XRay.clinic_id == clinic_b.id))
        assert b_client.get(f"/api/x-rays/{restored.id}/verify").get_json()["data"]["verified"] is False
        print("PASS: Images already damaged in the database are flagged in the backup and still restorable (and still reported).")

        # 6. Password is required and brute force is limited --------------------------------------
        db.session.query(AuthThrottle).delete()
        db.session.commit()
        codes = [_import(head_client, raw, password="wrong").status_code for _ in range(5)]
        assert codes[:4] == [403] * 4 and codes[4] == 429, codes
        assert count_clinic_rows(clinic.id) == before_a
        db.session.query(AuthThrottle).delete()
        db.session.commit()
        print("PASS: Import requires the head doctor's password and locks out repeated wrong guesses.")

        # 7. Damaged or tampered archives change nothing ------------------------------------------
        def expect_rejected(payload, fragment, label):
            db.session.query(AuthThrottle).delete()  # the 5-imports-per-hour limit is tested above
            db.session.commit()
            res = _import(head_client, payload)
            assert res.status_code in (400, 413), (label, res.status_code, res.data)
            assert fragment.lower() in res.get_json()["error"].lower(), (label, res.get_json())
            db.session.expire_all()
            assert count_clinic_rows(clinic.id) == before_a, label
            assert _snapshot(clinic.id) == original, label

        expect_rejected(b"not a zip", "not an AeroDent clinic backup", "not a zip")
        img_id = data["tables"]["xray_images"][0]["id"]
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            parts = {n: zf.read(n) for n in zf.namelist()}
        corrupt = bytearray(parts[f"xrays/{img_id}/data"])
        corrupt[-1] ^= 0xFF
        parts[f"xrays/{img_id}/data"] = bytes(corrupt)
        damaged = io.BytesIO()
        with zipfile.ZipFile(damaged, "w") as zf:
            for n, b in parts.items():
                zf.writestr(n, b)
        expect_rejected(damaged.getvalue(), "checksum", "corrupted X-ray")

        def dangling(files):
            payload = json.loads(files["data.json"])
            payload["tables"]["invoices"][0]["patient_id"] = 987654321
            files["data.json"] = json.dumps(payload).encode()
        expect_rejected(_rewrite(raw, dangling), "not in the backup", "dangling reference")

        def bad_enum(files):
            payload = json.loads(files["data.json"])
            payload["tables"]["appointments"][0]["status"] = "hacked"
            files["data.json"] = json.dumps(payload).encode()
        expect_rejected(_rewrite(raw, bad_enum), "not valid", "constraint violation")

        def bad_type(files):
            payload = json.loads(files["data.json"])
            payload["tables"]["patients"][0]["dob"] = "yesterday"
            files["data.json"] = json.dumps(payload).encode()
        expect_rejected(_rewrite(raw, bad_type), "invalid value", "bad date")

        def extra_file(files):
            files["../../etc/passwd"] = b"x"
        expect_rejected(_rewrite(raw, extra_file), "unexpected files", "path traversal entry")

        def unknown_column(files):
            payload = json.loads(files["data.json"])
            payload["tables"]["patients"][0]["clinic_secret"] = 1
            files["data.json"] = json.dumps(payload).encode()
        expect_rejected(_rewrite(raw, unknown_column), "newer version", "unknown column")

        def smuggle_clinic(files):
            payload = json.loads(files["data.json"])
            payload["tables"]["patients"][0]["clinic_id"] = clinic_b.id
            files["data.json"] = json.dumps(payload).encode()
        db.session.query(AuthThrottle).delete()
        db.session.commit()
        res = _import(head_client, _rewrite(raw, smuggle_clinic))
        assert res.status_code == 200, res.data
        db.session.expire_all()
        assert count_clinic_rows(clinic_b.id) == counts_b
        print("PASS: Corrupt, dangling, invalid, oversized-path and foreign-clinic archives are rejected or neutralised; nothing half-imported.")
    finally:
        db.session.rollback()
        db.session.query(AuthThrottle).delete()
        from backend.routes.admin import purge_clinic_data
        for clinic_id in clinic_ids:
            purge_clinic_data(clinic_id)
        db.session.commit()
        ctx.pop()

    print("\n================================================================")
    print("ALL CLINIC BACKUP TESTS PASSED")
    print("================================================================\n")


if __name__ == "__main__":
    run_clinic_backup_tests()
