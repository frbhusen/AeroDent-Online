import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import uuid
from decimal import Decimal

from backend.app import app
from backend.auth.service import hash_password
from backend.extensions import db
from backend.models import Clinic, Invoice, Patient, Treatment, User


TEST_PASSWORD = "TestPassword123!"


def run_odontogram_billing_tests():
    suffix = uuid.uuid4().hex[:8]
    head_email = f"bill-head-{suffix}@aerodent.local"
    secretary_email = f"bill-sec-{suffix}@aerodent.local"

    with app.app_context():
        clinic = Clinic(
            name=f"Billing Clinic {suffix}",
            currency="USD",
            is_active=True,
            subscription_status="active",
            procedure_prices={"filling": "50.00", "crown": "200.00"},
        )
        db.session.add(clinic)
        db.session.flush()
        head = User(
            clinic_id=clinic.id,
            name="Billing Head",
            email=head_email,
            password_hash=hash_password(TEST_PASSWORD),
            role="head_doctor",
            is_active=True,
        )
        secretary = User(
            clinic_id=clinic.id,
            name="Billing Secretary",
            email=secretary_email,
            password_hash=hash_password(TEST_PASSWORD),
            role="secretary",
            is_active=True,
        )
        db.session.add_all([head, secretary])
        db.session.flush()
        patient = Patient(clinic_id=clinic.id, created_by=head.id, name=f"Billing Patient {suffix}")
        db.session.add(patient)
        db.session.commit()
        clinic_id, patient_id = clinic.id, patient.id

        url = lambda mode, number: f"/api/patients/{patient_id}/odontogram/{mode}/{number}"  # noqa: E731

        def treatments(tooth=None):
            query = db.select(Treatment).where(Treatment.patient_id == patient_id).order_by(Treatment.id)
            return db.session.scalars(query).all()

        def invoices():
            return db.session.scalars(
                db.select(Invoice).where(Invoice.patient_id == patient_id).order_by(Invoice.id)
            ).all()

        try:
            with app.test_client() as client:
                res = client.post("/api/auth/login", json={"email": head_email, "password": TEST_PASSWORD})
                assert res.status_code == 200, res.json

                # 1. A procedure creates a completed treatment and an unpaid invoice at the list price
                res = client.put(url("permanent", 8), json={"condition": "filling", "procedure": "Filling"})
                assert res.status_code == 201, res.json
                assert res.json["billing"]["action"] == "created"
                db.session.expire_all()
                (treatment,) = treatments()
                (invoice,) = invoices()
                assert treatment.fee == Decimal("50.00") and treatment.status == "completed"
                assert treatment.tooth_number == 8 and treatment.procedure == "Filling"
                assert invoice.treatment_id == treatment.id and invoice.amount == Decimal("50.00")
                assert invoice.balance == Decimal("50.00") and invoice.status == "unpaid"
                print("PASS: A filling creates a treatment and an unpaid invoice at the price-list fee.")

                # 2. Saving only a note does not bill again
                res = client.put(url("permanent", 8), json={"condition": "filling", "notes": "mesial"})
                assert res.status_code == 200 and res.json["billing"] is None
                db.session.expire_all()
                assert len(treatments()) == 1 and len(invoices()) == 1
                print("PASS: Editing a note does not create duplicate billing.")

                # 3. Changing the procedure updates the same treatment and invoice
                res = client.put(url("permanent", 8), json={"condition": "crown", "procedure": "Crown"})
                assert res.json["billing"]["action"] == "updated"
                db.session.expire_all()
                (treatment,) = treatments()
                (invoice,) = invoices()
                assert treatment.procedure == "Crown" and treatment.fee == Decimal("200.00")
                assert invoice.amount == Decimal("200.00") and invoice.balance == Decimal("200.00")
                print("PASS: Changing the procedure re-prices the same treatment and invoice.")

                # 4. Downgrading to a finding voids the unpaid billing
                res = client.put(url("permanent", 8), json={"condition": "decay", "procedure": "Decay"})
                assert res.json["billing"]["action"] == "cancelled"
                db.session.expire_all()
                (treatment,) = treatments()
                (invoice,) = invoices()
                assert treatment.status == "cancelled"
                assert invoice.status == "cancelled" and invoice.balance == Decimal("0.00")
                print("PASS: Undoing a procedure cancels the unpaid treatment and invoice.")

                # 5. Fee override and "no invoice"; fee 0 without a price creates no invoice
                res = client.put(
                    url("permanent", 9),
                    json={"condition": "filling", "fee": "75", "create_invoice": False},
                )
                assert res.status_code == 201 and res.json["billing"]["invoice_id"] is None
                res = client.put(url("permanent", 10), json={"condition": "implant"})
                assert res.json["billing"]["fee"] == "0.00" and res.json["billing"]["invoice_id"] is None
                db.session.expire_all()
                fees = sorted(str(t.fee) for t in treatments() if t.status != "cancelled")
                assert fees == ["0.00", "75.00"], fees
                assert len(invoices()) == 1
                print("PASS: Fee override, create_invoice=false and zero-fee behave as expected.")

                # 6. Paid invoices are never rewritten; new work gets a new treatment
                res = client.put(url("permanent", 11), json={"condition": "filling"})
                invoice_id = res.json["billing"]["invoice_id"]
                res = client.post(
                    f"/api/invoices/{invoice_id}/payments",
                    json={"amount": 20, "payment_method": "cash"},
                )
                assert res.status_code == 201, res.json
                res = client.put(url("permanent", 11), json={"condition": "crown"})
                assert res.json["billing"]["action"] == "created"
                db.session.expire_all()
                paid = db.session.get(Invoice, invoice_id)
                assert paid.amount == Decimal("50.00") and paid.paid_amount == Decimal("20.00")
                tooth_11 = [t for t in treatments() if t.tooth_number == 11]
                assert len(tooth_11) == 2 and {t.procedure for t in tooth_11} == {"Filling", "Crown"}
                print("PASS: Paid billing is preserved; a new procedure gets its own treatment.")

                # 7. Clearing a tooth voids its unpaid billing
                res = client.put(url("permanent", 12), json={"condition": "rct"})
                assert res.status_code == 201
                res = client.delete(url("permanent", 12))
                assert res.status_code == 204
                db.session.expire_all()
                tooth_12 = [t for t in treatments() if t.tooth_number == 12]
                assert len(tooth_12) == 1 and tooth_12[0].status == "cancelled"
                print("PASS: Clearing a tooth cancels its unpaid billing.")

                # 8. Primary teeth are labelled and carry no permanent tooth number
                res = client.put(url("primary", 5), json={"condition": "filling"})
                assert res.status_code == 201
                db.session.expire_all()
                primary = [t for t in treatments() if t.tooth_number is None]
                assert len(primary) == 1 and "primary tooth E" in primary[0].description
                print("PASS: Primary-tooth treatments are described by letter.")

                # 9. Validation
                res = client.put(url("permanent", 13), json={"condition": "filling", "fee": "-5"})
                assert res.status_code == 422
                res = client.put(url("permanent", 13), json={"condition": "filling", "create_invoice": "yes"})
                assert res.status_code == 422
                print("PASS: Invalid billing hints are rejected.")

                # 10. Prices come back with the odontogram, and settings can update them
                res = client.get(f"/api/patients/{patient_id}/odontogram")
                assert res.json["meta"]["procedure_prices"] == {"filling": "50.00", "crown": "200.00"}
                res = client.patch(
                    "/api/settings",
                    json={"procedure_prices": {"rct": "120", "filling": ""}, "auto_invoice_odontogram": False},
                )
                assert res.status_code == 200, res.json
                assert res.json["data"]["procedure_prices"] == {"rct": "120.00"}
                assert res.json["data"]["auto_invoice_odontogram"] is False
                res = client.patch("/api/settings", json={"procedure_prices": {"botox": "5"}})
                assert res.status_code == 422
                res = client.put(url("permanent", 14), json={"condition": "rct"})
                assert res.json["billing"]["fee"] == "120.00" and res.json["billing"]["invoice_id"] is None
                print("PASS: Price list and auto-invoice setting are served, validated and honoured.")

            with app.test_client() as client:
                client.post("/api/auth/login", json={"email": secretary_email, "password": TEST_PASSWORD})
                res = client.put(url("permanent", 15), json={"condition": "filling"})
                assert res.status_code == 403
                print("PASS: Secretaries still cannot edit the odontogram.")

            print("\n==========================================")
            print("ALL ODONTOGRAM BILLING TESTS PASSED")
            print("==========================================")
        finally:
            from backend.routes.admin import purge_clinic_data

            db.session.rollback()
            purge_clinic_data(clinic_id)
            db.session.commit()


if __name__ == "__main__":
    run_odontogram_billing_tests()
