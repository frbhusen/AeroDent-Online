import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import os
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func

from backend.app import app
from backend.auth.service import hash_password
from backend.extensions import db
from backend.models import Clinic, User


TEST_PASSWORD = "TestPassword123!"


def run_super_admin_tests():
    suffix = uuid.uuid4().hex[:8]
    super_admin_email = f"super-{suffix}@aerodent.local"
    clinic_a_head_email = f"head-a-{suffix}@aerodent.local"
    clinic_a_doctor_email = f"doc-a-{suffix}@aerodent.local"
    clinic_a_sec_email = f"sec-a-{suffix}@aerodent.local"
    clinic_b_head_email = f"head-b-{suffix}@aerodent.local"
    clinic_b_doctor_email = f"doc-b-{suffix}@aerodent.local"

    with app.app_context():
        # Setup Super Admin
        super_admin = User(
            clinic_id=None,
            name="Super Admin Tester",
            email=super_admin_email,
            password_hash=hash_password(TEST_PASSWORD),
            role="super_admin",
            is_active=True,
        )
        # Setup Clinic A
        clinic_a = Clinic(
            name=f"Cascade Clinic A {suffix}",
            currency="SYR",
            is_active=True,
            subscription_status="active",
        )
        # Setup Clinic B
        clinic_b = Clinic(
            name=f"Independent Clinic B {suffix}",
            currency="SYR",
            is_active=True,
            subscription_status="active",
        )
        db.session.add_all([super_admin, clinic_a, clinic_b])
        db.session.flush()

        head_a = User(
            clinic_id=clinic_a.id,
            name="Head Doctor A",
            email=clinic_a_head_email,
            password_hash=hash_password(TEST_PASSWORD),
            role="head_doctor",
            is_active=True,
        )
        doc_a = User(
            clinic_id=clinic_a.id,
            name="Doctor A",
            email=clinic_a_doctor_email,
            password_hash=hash_password(TEST_PASSWORD),
            role="doctor",
            is_active=True,
        )
        sec_a = User(
            clinic_id=clinic_a.id,
            name="Secretary A",
            email=clinic_a_sec_email,
            password_hash=hash_password(TEST_PASSWORD),
            role="secretary",
            is_active=True,
        )

        head_b = User(
            clinic_id=clinic_b.id,
            name="Head Doctor B",
            email=clinic_b_head_email,
            password_hash=hash_password(TEST_PASSWORD),
            role="head_doctor",
            is_active=True,
        )
        doc_b = User(
            clinic_id=clinic_b.id,
            name="Doctor B",
            email=clinic_b_doctor_email,
            password_hash=hash_password(TEST_PASSWORD),
            role="doctor",
            is_active=True,
        )
        db.session.add_all([head_a, doc_a, sec_a, head_b, doc_b])
        db.session.commit()

        clinic_a_id = clinic_a.id
        clinic_b_id = clinic_b.id
        head_a_id = head_a.id
        doc_a_id = doc_a.id

        try:
            # 1. Test Super Admin Login
            with app.test_client() as client:
                res = client.post("/api/auth/login", json={"email": super_admin_email, "password": TEST_PASSWORD})
                assert res.status_code == 200, f"Super admin login failed: {res.json}"
                assert res.json["user"]["role"] == "super_admin"
                assert res.json["user"]["clinic_id"] is None
                print("PASS: Super admin can log in and has clinic_id=None.")

                # 2. Super Admin access to Admin API
                res_metrics = client.get("/api/admin/metrics")
                assert res_metrics.status_code == 200
                assert "total_clinics" in res_metrics.json["data"]
                print("PASS: Super admin can read platform metrics.")

                res_clinics = client.get("/api/admin/clinics")
                assert res_clinics.status_code == 200
                assert len(res_clinics.json["data"]) >= 2
                print("PASS: Super admin can list all clinics.")

                # 3. Super Admin blocked from clinical work
                res_clinical = client.get("/api/patients")
                assert res_clinical.status_code == 403
                print("PASS: Super admin is strictly blocked from clinical patient work.")

            # 4. Non-super admin blocked from Admin API
            with app.test_client() as client:
                client.post("/api/auth/login", json={"email": clinic_a_head_email, "password": TEST_PASSWORD})
                res = client.get("/api/admin/metrics")
                assert res.status_code == 403
                res = client.get("/api/admin/clinics")
                assert res.status_code == 403
                print("PASS: Head doctor is forbidden from accessing Super Admin API.")

            # 5. Head doctor cannot create another head doctor
            with app.test_client() as client:
                client.post("/api/auth/login", json={"email": clinic_a_head_email, "password": TEST_PASSWORD})
                # Attempt to create head_doctor
                res_create_head = client.post(
                    "/api/staff",
                    json={
                        "name": "New Head Doctor",
                        "email": f"new-head-{suffix}@aerodent.local",
                        "password": "Password123!",
                        "role": "head_doctor",
                    },
                )
                assert res_create_head.status_code == 403, f"Expected 403, got {res_create_head.status_code}"
                print("PASS: Head doctor cannot create another head doctor.")

                # Head doctor CAN create a regular doctor
                res_create_doc = client.post(
                    "/api/staff",
                    json={
                        "name": "New Junior Doctor",
                        "email": f"new-doc-{suffix}@aerodent.local",
                        "password": "Password123!",
                        "role": "doctor",
                    },
                )
                assert res_create_doc.status_code == 201
                new_doc_id = res_create_doc.json["data"]["id"]
                print("PASS: Head doctor can create regular doctors and staff.")

                # Head doctor CANNOT promote doctor to head_doctor
                res_promote = client.patch(
                    f"/api/staff/{new_doc_id}",
                    json={"role": "head_doctor"},
                )
                assert res_promote.status_code == 403
                print("PASS: Head doctor cannot promote staff to head doctor.")

            # 6. CASCADE DEACTIVATION: Deactivate Head Doctor A
            with app.test_client() as admin_client:
                admin_client.post("/api/auth/login", json={"email": super_admin_email, "password": TEST_PASSWORD})
                # Super admin deactivates Head Doctor A
                res_deact = admin_client.patch(
                    f"/api/admin/users/{head_a_id}",
                    json={"is_active": False},
                )
                assert res_deact.status_code == 200
                assert res_deact.json["data"]["is_active"] is False
                print("PASS: Super admin deactivated Head Doctor A.")

            # Now verify Head Doctor A cannot sign in
            with app.test_client() as client_head_a:
                res = client_head_a.post("/api/auth/login", json={"email": clinic_a_head_email, "password": TEST_PASSWORD})
                assert res.status_code in (401, 403)
                print("PASS: Inactive Head Doctor A cannot sign in.")

            # CRITICAL CASCADE RULE: Doctor A in Clinic A CANNOT sign in!
            with app.test_client() as client_doc_a:
                res = client_doc_a.post("/api/auth/login", json={"email": clinic_a_doctor_email, "password": TEST_PASSWORD})
                assert res.status_code == 403
                assert "head doctor account is inactive" in res.json["error"].lower()
                print("PASS: Doctor A is blocked from signing in because Head Doctor A is deactivated.")

            # CRITICAL CASCADE RULE: Secretary A in Clinic A CANNOT sign in!
            with app.test_client() as client_sec_a:
                res = client_sec_a.post("/api/auth/login", json={"email": clinic_a_sec_email, "password": TEST_PASSWORD})
                assert res.status_code == 403
                assert "head doctor account is inactive" in res.json["error"].lower()
                print("PASS: Secretary A is blocked from signing in because Head Doctor A is deactivated.")

            # INDEPENDENCE RULE: Clinic B is completely unaffected!
            with app.test_client() as client_head_b:
                res = client_head_b.post("/api/auth/login", json={"email": clinic_b_head_email, "password": TEST_PASSWORD})
                assert res.status_code == 200
                print("PASS: Clinic B Head Doctor signs in successfully and is unaffected.")

            with app.test_client() as client_doc_b:
                res = client_doc_b.post("/api/auth/login", json={"email": clinic_b_doctor_email, "password": TEST_PASSWORD})
                assert res.status_code == 200
                print("PASS: Clinic B Doctor signs in successfully and is unaffected.")

            # 7. Reactivate Head Doctor A -> Clinic A access restored
            with app.test_client() as admin_client:
                admin_client.post("/api/auth/login", json={"email": super_admin_email, "password": TEST_PASSWORD})
                res_react = admin_client.patch(
                    f"/api/admin/users/{head_a_id}",
                    json={"is_active": True},
                )
                assert res_react.status_code == 200

            with app.test_client() as client_doc_a:
                res = client_doc_a.post("/api/auth/login", json={"email": clinic_a_doctor_email, "password": TEST_PASSWORD})
                assert res.status_code == 200
                print("PASS: Reactivating Head Doctor A restores access for Doctor A.")

            # 8. Subscription Expiration / Clinic Deactivation Check
            with app.test_client() as admin_client:
                admin_client.post("/api/auth/login", json={"email": super_admin_email, "password": TEST_PASSWORD})
                # Deactivate entire Clinic A
                res_clinic_deact = admin_client.patch(
                    f"/api/admin/clinics/{clinic_a_id}",
                    json={"is_active": False},
                )
                assert res_clinic_deact.status_code == 200

            with app.test_client() as client_doc_a:
                res = client_doc_a.post("/api/auth/login", json={"email": clinic_a_doctor_email, "password": TEST_PASSWORD})
                assert res.status_code == 403
                assert "clinic account has been deactivated" in res.json["error"].lower()
                print("PASS: Deactivated clinic blocks all sign-ins.")

            # 9. Super Admin subscription extend
            with app.test_client() as admin_client:
                admin_client.post("/api/auth/login", json={"email": super_admin_email, "password": TEST_PASSWORD})
                res_extend = admin_client.patch(
                    f"/api/admin/clinics/{clinic_a_id}",
                    json={"is_active": True, "extend_days": 30, "subscription_status": "active"},
                )
                assert res_extend.status_code == 200
                assert res_extend.json["data"]["is_active"] is True
                assert res_extend.json["data"]["subscription_status"] == "active"
                assert res_extend.json["data"]["subscription_expires_at"] is not None
                print("PASS: Super admin can extend subscriptions and reactivate clinics.")

            # 10. Super Admin create clinic with head doctor
            with app.test_client() as admin_client:
                admin_client.post("/api/auth/login", json={"email": super_admin_email, "password": TEST_PASSWORD})
                res_new_clinic = admin_client.post(
                    "/api/admin/clinics",
                    json={
                        "name": f"Created By Super Admin {suffix}",
                        "phone": "123456789",
                        "head_doctor_name": "Newly Created Head",
                        "head_doctor_email": f"created-head-{suffix}@aerodent.local",
                        "head_doctor_password": "SecurePassword123!",
                        "subscription_status": "active",
                    },
                )
                created_clinic_id = res_new_clinic.json["data"]["id"]
                created_head_email = f"created-head-{suffix}@aerodent.local"
                print("PASS: Super admin can create new clinics and their initial head doctor.")

                # 11. Super Admin delete clinic (cascade deletes all staff and records)
                res_del_clinic = admin_client.delete(f"/api/admin/clinics/{created_clinic_id}")
                assert res_del_clinic.status_code == 204
                # Verify clinic is deleted
                assert db.session.get(Clinic, created_clinic_id) is None
                # Verify all staff of that clinic are also deleted!
                deleted_staff = db.session.scalar(
                    db.select(func.count(User.id)).where(User.email == created_head_email)
                )
                assert deleted_staff == 0
                # Verify Clinic A and Clinic B still exist
                assert db.session.get(Clinic, clinic_a_id) is not None
                assert db.session.get(Clinic, clinic_b_id) is not None
                print("PASS: Super admin can delete clinic and all its staff are deleted too.")

            print("\n==========================================")
            print("ALL SUPER ADMIN & SUBSCRIPTION TESTS PASSED")
            print("==========================================")

        finally:
            # Cleanup test records
            with app.app_context():
                from backend.routes.admin import purge_clinic_data
                for cid in [clinic_a_id, clinic_b_id]:
                    if cid:
                        purge_clinic_data(cid)
                for c in Clinic.query.filter(Clinic.name == f"Created By Super Admin {suffix}").all():
                    purge_clinic_data(c.id)
                User.query.filter(User.email == super_admin_email).delete(synchronize_session=False)
                db.session.commit()


if __name__ == "__main__":
    run_super_admin_tests()
