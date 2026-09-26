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
from backend.models.audit_log import AuditLog


TEST_PASSWORD = "Correct Invoice Password!"


def create_user(clinic_id, role, suffix):
    return User(
        clinic_id=clinic_id,
        name=f"{role} {suffix}",
        email=f"invoice-{role}-{suffix}@aerodent.local",
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
        date=date(2026, 9, 21),
        status="planned",
        fee=Decimal("50000.00"),
        description=description,
        procedure="filling",
    )
    db.session.add(treatment)
    db.session.flush()
    return treatment


def invoice_payload(patient_id, **overrides):
    payload = {
        "patient_id": patient_id,
        "amount": "50000",
        "discount": "0",
        "paid_amount": "0",
        "status": "paid",
    }
    payload.update(overrides)
    return payload


def run_invoice_tests():
    suffix = uuid4().hex
    with app.app_context():
        clinic_a = Clinic(
            name=f"Invoice Test A {suffix}",
            currency="SYR",
            work_start=time(9, 0),
            work_end=time(18, 0),
            slot_duration=30,
        )
        clinic_b = Clinic(
            name=f"Invoice Test B {suffix}",
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
            clinic_a.id, patient_a.id, doctor_a.id, doctor_a.id, "Clinic A treatment"
        )
        treatment_b = create_treatment(
            clinic_b.id, patient_b.id, doctor_b.id, doctor_b.id, "Clinic B treatment"
        )
        db.session.commit()

        patient_a_id = patient_a.id
        patient_b_id = patient_b.id
        treatment_a_id = treatment_a.id
        treatment_b_id = treatment_b.id
        clinic_a_id = clinic_a.id
        try:
            with app.test_client() as client:
                for method, url, kwargs in (
                    ("get", "/api/invoices", {}),
                    ("get", "/api/invoices/1", {}),
                    ("post", "/api/invoices", {"json": invoice_payload(patient_a_id)}),
                    ("patch", "/api/invoices/1", {"json": {"paid_amount": "1"}}),
                    ("delete", "/api/invoices/1", {}),
                ):
                    assert getattr(client, method)(url, **kwargs).status_code == 401
                print("PASS: Unauthenticated invoice operations return 401.")

            with app.test_client() as client:
                login(client, doctor_a)
                response = client.post(
                    "/api/invoices",
                    json=invoice_payload(
                        patient_a_id,
                        treatment_id=treatment_a_id,
                        clinic_id=999999,
                        created_by=999999,
                        balance=999999,
                    ),
                )
                assert response.status_code == 400
                response = client.post(
                    "/api/invoices",
                    json=invoice_payload(patient_a_id, treatment_id=treatment_a_id),
                )
                assert response.status_code == 201
                invoice_id = response.json["data"]["id"]
                invoice = db.session.get(Invoice, invoice_id)
                assert invoice.clinic_id == clinic_a_id
                assert invoice.created_by == doctor_a.id
                assert invoice.balance == Decimal("50000.00")
                assert invoice.status == "unpaid"
                print("PASS: Ownership is server controlled and financial status is derived.")

                for amount, discount, paid, expected_balance, expected_status in (
                    ("50000", "0", "20000", "30000.00", "partially-paid"),
                    ("50000", "5000", "45000", "0.00", "paid"),
                ):
                    response = client.post(
                        "/api/invoices",
                        json=invoice_payload(
                            patient_a_id,
                            amount=amount,
                            discount=discount,
                            paid_amount=paid,
                            status="unpaid",
                        ),
                    )
                    assert response.status_code == 201
                    assert response.json["data"]["balance"] == expected_balance
                    assert response.json["data"]["status"] == expected_status
                print("PASS: Decimal amount, discount, paid amount, balance, and status work.")

                invalid_values = [
                    {"amount": -1},
                    {"discount": -1},
                    {"paid_amount": -1},
                    {"discount": 50001},
                    {"paid_amount": 50001},
                    {"amount": "abc"},
                    {"discount": {}},
                    {"paid_amount": []},
                    {"status": "invalid"},
                ]
                for values in invalid_values:
                    assert client.post(
                        "/api/invoices",
                        json=invoice_payload(patient_a_id, **values),
                    ).status_code in {400, 422}
                print("PASS: Invalid money values and statuses are rejected.")

                response = client.post(
                    "/api/invoices",
                    json=invoice_payload(patient_a_id, treatment_id=treatment_b_id),
                )
                assert response.status_code == 404
                response = client.post(
                    "/api/invoices",
                    json=invoice_payload(patient_b_id),
                )
                assert response.status_code == 404
                response = client.post(
                    "/api/invoices",
                    json=invoice_payload(patient_a_id, treatment_id=999999),
                )
                assert response.status_code == 404
                mismatch_patient = create_patient(clinic_a.id, doctor_a.id, "Mismatch Patient")
                db.session.commit()
                assert client.post(
                    "/api/invoices",
                    json=invoice_payload(mismatch_patient.id, treatment_id=treatment_a_id),
                ).status_code == 400
                print("PASS: Patient, treatment, and relationship ownership are validated.")

                response = client.patch(
                    f"/api/invoices/{invoice_id}",
                    json={"paid_amount": "20000", "balance": "999999"},
                )
                assert response.status_code == 400
                response = client.patch(
                    f"/api/invoices/{invoice_id}",
                    json={"paid_amount": "20000"},
                )
                assert response.status_code == 200
                assert response.json["data"]["balance"] == "30000.00"
                assert response.json["data"]["status"] == "partially-paid"
                assert response.json["data"]["amount"] == "50000.00"
                print("PASS: Partial PATCH recalculates balance and status.")

                response = client.get("/api/invoices", query_string={"patient_id": patient_a_id})
                assert response.status_code == 200
                assert response.json["meta"]["total"] >= 1
                response = client.get("/api/invoices", query_string={"status": "partially-paid"})
                assert response.status_code == 200
                response = client.get("/api/invoices", query_string={"page": 1, "per_page": 1})
                assert response.status_code == 200
                assert response.json["meta"]["per_page"] == 1
                print("PASS: Invoice filters and pagination work.")

            with app.test_client() as client:
                login(client, secretary_a)
                assert client.get("/api/invoices").status_code == 200
                response = client.post(
                    "/api/invoices", json=invoice_payload(patient_a_id)
                )
                assert response.status_code == 201
                secretary_invoice_id = response.json["data"]["id"]
                assert client.patch(
                    f"/api/invoices/{secretary_invoice_id}",
                    json={"paid_amount": "100"},
                ).status_code == 200
                assert client.delete(f"/api/invoices/{secretary_invoice_id}").status_code == 403
                print("PASS: Secretary can read/create/update but cannot delete invoices.")

            with app.test_client() as client:
                login(client, doctor_a)
                assert client.delete(f"/api/invoices/{invoice_id}").status_code == 403
                assert client.get(f"/api/invoices/{invoice_id}").status_code == 200
                assert client.get(f"/api/invoices/999999").status_code == 404
                assert client.post(
                    "/api/invoices", json=invoice_payload(patient_b_id)
                ).status_code == 404
                print("PASS: Doctor delete permission and same-clinic access are enforced.")

            with app.test_client() as client:
                login(client, doctor_b)
                response = client.post(
                    "/api/invoices",
                    json=invoice_payload(patient_b_id, treatment_id=treatment_b_id),
                )
                assert response.status_code == 201
                clinic_b_invoice_id = response.json["data"]["id"]

            with app.test_client() as client:
                login(client, head_a)
                assert client.get(f"/api/invoices/{clinic_b_invoice_id}").status_code == 404
                assert client.patch(
                    f"/api/invoices/{clinic_b_invoice_id}", json={"paid_amount": "1"}
                ).status_code == 404
                assert client.delete(f"/api/invoices/{clinic_b_invoice_id}").status_code == 404
                print("PASS: Cross-clinic invoice access returns 404.")

            with app.test_client() as client:
                login(client, head_a)
                response = client.post(
                    "/api/invoices", json=invoice_payload(patient_a_id)
                )
                assert response.status_code == 201
                head_invoice_id = response.json["data"]["id"]

                created_log = db.session.scalar(
                    db.select(AuditLog).where(
                        AuditLog.action == "invoice_created",
                        AuditLog.resource_id == str(head_invoice_id),
                    )
                )
                assert created_log is not None, "Expected an invoice_created audit log entry."

                assert client.delete(f"/api/invoices/{head_invoice_id}").status_code == 204
                assert db.session.get(Invoice, head_invoice_id) is None

                deleted_log = db.session.scalar(
                    db.select(AuditLog).where(
                        AuditLog.action == "invoice_deleted",
                        AuditLog.resource_id == str(head_invoice_id),
                    )
                )
                assert deleted_log is not None, "Expected an invoice_deleted audit log entry."
                print("PASS: Head doctor can delete invoices without deleting clinical records.")
                print("PASS: Invoice creation and deletion are audit-logged.")
        finally:
            db.session.delete(clinic_a)
            db.session.delete(clinic_b)
            db.session.commit()


if __name__ == "__main__":
    run_invoice_tests()
    print()
    print("==========================================")
    print("ALL INVOICE API TESTS PASSED")
    print("==========================================")
