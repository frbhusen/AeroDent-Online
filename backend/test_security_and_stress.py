import sys
from pathlib import Path
from decimal import Decimal
from datetime import date, time, timedelta
from uuid import uuid4

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.app import app
from backend.extensions import db
from backend.models import Clinic, User, Patient, Invoice, Payment
from backend.auth.service import hash_password


def run_security_and_stress_tests():
    suffix = uuid4().hex[:8]
    clinic_email = f"stress-head-{suffix}@aerodent.local"
    attacker_email = f"stress-attacker-{suffix}@aerodent.local"

    with app.app_context():
        # Setup Test Clinics & Users
        clinic_a = Clinic(
            name=f"Stress Clinic A {suffix}",
            currency="SYR",
            work_start=time(9, 0),
            work_end=time(18, 0),
            slot_duration=30,
            is_active=True,
        )
        clinic_b = Clinic(
            name=f"Stress Clinic B {suffix}",
            currency="SYR",
            work_start=time(9, 0),
            work_end=time(18, 0),
            slot_duration=30,
            is_active=True,
        )
        db.session.add_all([clinic_a, clinic_b])
        db.session.flush()

        head_user = User(
            clinic_id=clinic_a.id,
            name="Stress Head Doctor",
            email=clinic_email,
            password_hash=hash_password("Password123!"),
            role="head_doctor",
            is_active=True,
        )
        attacker_user = User(
            clinic_id=clinic_b.id,
            name="Stress Attacker Doctor",
            email=attacker_email,
            password_hash=hash_password("Password123!"),
            role="doctor",
            is_active=True,
        )
        db.session.add_all([head_user, attacker_user])
        db.session.flush()

        patient_a = Patient(
            clinic_id=clinic_a.id,
            name="Stress Patient A",
            phone="+963911111111",
            created_by=head_user.id,
        )
        db.session.add(patient_a)
        db.session.flush()

        invoice_a = Invoice(
            clinic_id=clinic_a.id,
            patient_id=patient_a.id,
            amount=Decimal("50000.00"),
            discount=Decimal("0.00"),
            paid_amount=Decimal("0.00"),
            balance=Decimal("50000.00"),
            status="unpaid",
            created_by=head_user.id,
        )
        db.session.add(invoice_a)
        db.session.commit()

        try:
            # 1. TEST: HTTP Security Headers
            with app.test_client() as client:
                res = client.get("/api/auth/me")
                assert res.headers.get("X-Content-Type-Options") == "nosniff", "Missing X-Content-Type-Options"
                assert res.headers.get("X-Frame-Options") == "SAMEORIGIN", "Missing X-Frame-Options"
                assert res.headers.get("X-XSS-Protection") == "1; mode=block", "Missing X-XSS-Protection"
                assert res.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin", "Missing Referrer-Policy"
                assert "geolocation=()" in res.headers.get("Permissions-Policy", ""), "Missing Permissions-Policy"
                print("PASS: All critical HTTP security headers are enforced.")

            # 2. TEST: Global CSRF / Cross-Origin Protection on state-changing API endpoints
            with app.test_client() as client:
                # Login as head doctor
                login_res = client.post("/api/auth/login", json={"email": clinic_email, "password": "Password123!"})
                assert login_res.status_code == 200

                # Attacker website attempts cross-origin POST /api/patients
                csrf_res = client.post(
                    "/api/patients",
                    json={"name": "CSRF Injected Patient"},
                    headers={"Origin": "https://malicious-website.com"},
                )
                assert csrf_res.status_code == 403, f"Expected 403 for cross-origin POST, got {csrf_res.status_code}"

                # Attacker website attempts cross-origin DELETE /api/invoices
                csrf_del = client.delete(
                    f"/api/invoices/{invoice_a.id}",
                    headers={"Origin": "https://malicious-website.com"},
                )
                assert csrf_del.status_code == 403, f"Expected 403 for cross-origin DELETE, got {csrf_del.status_code}"
                print("PASS: Global cross-origin CSRF protection strictly blocks unauthorized third-party origins.")

            # 3. TEST: Financial Overflow & Negative Amount Rejection
            with app.test_client() as client:
                client.post("/api/auth/login", json={"email": clinic_email, "password": "Password123!"})

                # Massive numeric overflow attempt on payment
                overflow_res = client.post(
                    f"/api/invoices/{invoice_a.id}/payments",
                    json={"amount": "9999999999999999999999999.00"},
                )
                assert overflow_res.status_code in (400, 422), f"Expected 400/422 for overflow amount, got {overflow_res.status_code}"

                # Negative amount attempt on payment
                neg_res = client.post(
                    f"/api/invoices/{invoice_a.id}/payments",
                    json={"amount": "-500.00"},
                )
                assert neg_res.status_code == 400, f"Expected 400 for negative amount, got {neg_res.status_code}"

                # Non-finite amount attempt (e.g. NaN or Inf)
                inf_res = client.post(
                    f"/api/invoices/{invoice_a.id}/payments",
                    json={"amount": "NaN"},
                )
                assert inf_res.status_code == 400

                # Valid payment works cleanly
                valid_res = client.post(
                    f"/api/invoices/{invoice_a.id}/payments",
                    json={"amount": "15000.00", "payment_method": "cash"},
                )
                assert valid_res.status_code == 201
                assert valid_res.json["invoice"]["balance"] == 35000.00
                print("PASS: Financial overflow and invalid amounts are safely validated without database errors.")

            # 4. TEST: String Length Limits & Buffer Protection
            with app.test_client() as client:
                client.post("/api/auth/login", json={"email": clinic_email, "password": "Password123!"})

                # Oversized patient name (> 200 chars)
                oversized_res = client.post(
                    "/api/patients",
                    json={"name": "A" * 300},
                )
                assert oversized_res.status_code == 422
                assert "too long" in oversized_res.json["error"]

                # Oversized phone number (> 50 chars)
                oversized_phone = client.post(
                    "/api/patients",
                    json={"name": "Normal Name", "phone": "0" * 80},
                )
                assert oversized_phone.status_code == 422
                assert "too long" in oversized_phone.json["error"]
                print("PASS: String length limits prevent database truncation and overflow errors.")

            # 5. TEST: Cross-Tenant Data Isolation Under Attack
            with app.test_client() as client:
                # Login as attacker from Clinic B
                client.post("/api/auth/login", json={"email": attacker_email, "password": "Password123!"})

                # Attacker tries to read Clinic A's patient
                pt_read = client.get(f"/api/patients/{patient_a.id}")
                assert pt_read.status_code == 404

                # Attacker tries to read Clinic A's invoice
                inv_read = client.get(f"/api/invoices/{invoice_a.id}")
                assert inv_read.status_code == 404

                # Attacker tries to add a payment to Clinic A's invoice
                pay_hack = client.post(f"/api/invoices/{invoice_a.id}/payments", json={"amount": "100.00"})
                assert pay_hack.status_code == 404

                # Attacker tries to access Clinic A's timeline
                tl_read = client.get(f"/api/patients/{patient_a.id}/timeline")
                assert tl_read.status_code == 404
                print("PASS: Cross-tenant data isolation strictly prevents any cross-clinic data leakage or manipulation.")

            # 6. TEST: Rate Limiting Stress Test
            with app.test_client() as client:
                blocked = False
                for _ in range(30):
                    resp = client.post(
                        "/api/auth/login",
                        json={"email": clinic_email, "password": "WrongPassword!"},
                    )
                    if resp.status_code == 429:
                        blocked = True
                        break
                assert blocked, "Rate limiter failed to block brute force attempts"
                print("PASS: Rate limiter successfully protects against credential brute-forcing.")

            # 6b. Spoofing X-Forwarded-For must not reset the per-client rate-limit bucket
            # unless the app is explicitly configured to trust a reverse proxy for it.
            with app.test_client() as client:
                still_blocked_after_spoofing = False
                for i in range(30):
                    resp = client.post(
                        "/api/auth/login",
                        json={"email": clinic_email, "password": "WrongPassword!"},
                        headers={"X-Forwarded-For": f"10.0.0.{i % 250}"},
                    )
                    if resp.status_code == 429:
                        still_blocked_after_spoofing = True
                        break
                assert still_blocked_after_spoofing, (
                    "A spoofed X-Forwarded-For header bypassed the login rate limiter"
                )
                print("PASS: Spoofed X-Forwarded-For does not bypass the rate limiter.")

        finally:
            # Clean up
            db.session.rollback()
            Payment.query.filter_by(clinic_id=clinic_a.id).delete()
            Invoice.query.filter_by(clinic_id=clinic_a.id).delete()
            Patient.query.filter_by(clinic_id=clinic_a.id).delete()
            User.query.filter(User.email.in_([clinic_email, attacker_email])).delete()
            Clinic.query.filter(Clinic.id.in_([clinic_a.id, clinic_b.id])).delete()
            db.session.commit()


if __name__ == "__main__":
    run_security_and_stress_tests()
    print()
    print("================================================================")
    print("ALL SECURITY & STRESS TESTS PASSED")
    print("================================================================")
