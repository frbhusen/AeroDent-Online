import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from datetime import date
from decimal import Decimal

from backend.app import app
from backend.extensions import db
from backend.models import Clinic, Invoice, Patient, Payment, User


def run_tests():
    print("Starting tests for Audit Logs, Installment Payments & Self-Service Registration...")
    client = app.test_client()

    clinic_id = None
    try:
        with app.app_context():
            # 1. Test Self-Service Registration
            import uuid
            uid = uuid.uuid4().hex[:6]
            test_email = f"sarah.{uid}@trialclinic.com"
            reg_payload = {
                "clinic_name": f"Smile Care Trial {uid}",
                "head_doctor_name": "Dr. Sarah Smile",
                "email": test_email,
                "password": "Password123!",
                "phone": "+963991234567",
            }
            # Self-registration is disabled by default (trial requests go through the contact
            # page); this test covers the optional self-service mode explicitly.
            disabled = client.post("/api/auth/register", json=reg_payload)
            assert disabled.status_code == 403, disabled.data
            app.config["ALLOW_SELF_REGISTRATION"] = True
            res = client.post("/api/auth/register", json=reg_payload)
            assert res.status_code == 201, f"Expected 201, got {res.status_code}: {res.data}"
            data = res.get_json()
            assert data["user"]["email"] == test_email
            assert data["user"]["role"] == "head_doctor"
            assert data["clinic"]["subscription_status"] == "trial"
            clinic_id = data["clinic"]["id"]
            print("PASS: Self-service trial registration created clinic and head doctor.")

            # 2. Duplicate registration rejected
            res_dup = client.post("/api/auth/register", json=reg_payload)
            assert res_dup.status_code == 409, f"Expected 409, got {res_dup.status_code}"
            print("PASS: Duplicate registration blocked with 409.")

            # 3. Create a patient under the new clinic
            patient_res = client.post("/api/patients", json={
                "name": "Jane Patient",
                "phone": "+963999888777",
                "dob": "1995-05-15",
                "gender": "female",
            })
            assert patient_res.status_code == 201, f"Expected 201, got {patient_res.status_code}"
            patient_id = patient_res.get_json()["data"]["id"]
            print("PASS: Created patient under trial clinic.")

            # 4. Create an invoice for 500.00
            invoice = Invoice(
                clinic_id=clinic_id,
                patient_id=patient_id,
                amount=Decimal("500.00"),
                discount=Decimal("50.00"),
                paid_amount=Decimal("0.00"),
                balance=Decimal("450.00"),
                status="unpaid",
            )
            db.session.add(invoice)
            db.session.commit()
            invoice_id = invoice.id

            # 5. Record an installment payment of 200.00
            pay_res = client.post(f"/api/invoices/{invoice_id}/payments", json={
                "amount": 200.00,
                "payment_method": "cash",
                "notes": "First installment paid in cash",
            })
            assert pay_res.status_code == 201, f"Expected 201, got {pay_res.status_code}: {pay_res.data}"
            pay_data = pay_res.get_json()
            assert pay_data["invoice"]["paid_amount"] == 200.00
            assert pay_data["invoice"]["balance"] == 250.00
            assert pay_data["invoice"]["status"] == "partially-paid"
            print("PASS: Installment payment recorded, status updated to partially-paid.")

            # 6. Record second installment of 250.00 (fully paying off)
            pay_res2 = client.post(f"/api/invoices/{invoice_id}/payments", json={
                "amount": 250.00,
                "payment_method": "card",
                "notes": "Final payment via credit card",
            })
            assert pay_res2.status_code == 201
            pay_data2 = pay_res2.get_json()
            assert pay_data2["invoice"]["paid_amount"] == 450.00
            assert pay_data2["invoice"]["balance"] == 0.00
            assert pay_data2["invoice"]["status"] == "paid"
            print("PASS: Final installment paid in full, status updated to paid.")

            # 6b. Attempting to overpay a fully-paid invoice is rejected and leaves it unchanged
            overpay_res = client.post(f"/api/invoices/{invoice_id}/payments", json={
                "amount": 0.01,
                "payment_method": "cash",
            })
            assert overpay_res.status_code == 422, f"Expected 422, got {overpay_res.status_code}: {overpay_res.data}"
            db.session.expire_all()
            refreshed_invoice = db.session.get(Invoice, invoice_id)
            assert refreshed_invoice.paid_amount == Decimal("450.00")
            assert refreshed_invoice.balance == Decimal("0.00")
            print("PASS: Overpayment beyond the payable amount is rejected and invoice is unchanged.")

            # 6c. Invalid payment_method / payment_date are rejected, not silently coerced
            validation_invoice = Invoice(
                clinic_id=clinic_id,
                patient_id=patient_id,
                amount=Decimal("100.00"),
                discount=Decimal("0.00"),
                paid_amount=Decimal("0.00"),
                balance=Decimal("100.00"),
                status="unpaid",
            )
            db.session.add(validation_invoice)
            db.session.commit()
            validation_invoice_id = validation_invoice.id

            bad_method_res = client.post(f"/api/invoices/{validation_invoice_id}/payments", json={
                "amount": 10.00,
                "payment_method": "bogus",
            })
            assert bad_method_res.status_code == 422, f"Expected 422, got {bad_method_res.status_code}"

            bad_date_res = client.post(f"/api/invoices/{validation_invoice_id}/payments", json={
                "amount": 10.00,
                "payment_method": "cash",
                "payment_date": "not-a-date",
            })
            assert bad_date_res.status_code == 422, f"Expected 422, got {bad_date_res.status_code}"
            print("PASS: Invalid payment_method and payment_date are rejected instead of silently replaced.")

            # 7. List payments for invoice
            list_res = client.get(f"/api/invoices/{invoice_id}/payments")
            assert list_res.status_code == 200
            payments_list = list_res.get_json()["data"]
            assert len(payments_list) == 2
            print("PASS: Listed 2 payments for invoice.")

            # 8. Check Audit Logs as Head Doctor
            audit_res = client.get("/api/audit-logs")
            assert audit_res.status_code == 200, f"Expected 200, got {audit_res.status_code}"
            audit_items = audit_res.get_json()["data"]
            actions = [a["action"] for a in audit_items]
            assert "clinic_registered" in actions
            assert "patient_created" in actions
            assert "payment_received" in actions
            print("PASS: Head doctor can retrieve clinic audit logs containing all actions.")

            # 9. Super Admin login and cross-clinic audit inspection
            client.post("/api/auth/logout")
            from backend.seed import get_or_create_super_admin, SUPER_ADMIN_EMAIL, SUPER_ADMIN_PASSWORD
            get_or_create_super_admin()
            db.session.commit()

            admin_login = client.post("/api/auth/login", json={
                "email": SUPER_ADMIN_EMAIL,
                "password": SUPER_ADMIN_PASSWORD,
            })
            assert admin_login.status_code == 200, f"Expected 200, got {admin_login.status_code}: {admin_login.data}"

            admin_audit = client.get(f"/api/audit-logs?clinic_id={clinic_id}")
            assert admin_audit.status_code == 200
            assert len(admin_audit.get_json()["data"]) >= 3
            print("PASS: Super admin can inspect audit logs for any clinic.")
    finally:
        if clinic_id:
            with app.app_context():
                from backend.routes.admin import purge_clinic_data
                purge_clinic_data(clinic_id)
                db.session.commit()
            print("PASS: Deleted test trial clinic cleanly.")

    print("\n========================================================")
    print("ALL AUDIT, PAYMENTS & REGISTRATION TESTS PASSED (100%)")
    print("========================================================\n")


if __name__ == "__main__":
    run_tests()
