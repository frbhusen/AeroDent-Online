import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import uuid

from backend.app import app
from backend.auth.service import hash_password
from backend.extensions import db
from backend.models import Clinic, User


TEST_PASSWORD = "TestPassword123!"


def _staff_payload(suffix, tag, role):
    return {
        "name": f"{tag} {suffix}",
        "email": f"{tag}-{suffix}@aerodent.local",
        "password": TEST_PASSWORD,
        "role": role,
    }


def run_seat_limit_tests():
    suffix = uuid.uuid4().hex[:8]
    head_email = f"seat-head-{suffix}@aerodent.local"
    super_email = f"seat-super-{suffix}@aerodent.local"

    with app.app_context():
        clinic = Clinic(
            name=f"Seat Clinic {suffix}",
            currency="SYR",
            is_active=True,
            subscription_status="active",
            max_doctors=1,
            max_secretaries=1,
        )
        db.session.add(clinic)
        db.session.flush()
        db.session.add_all(
            [
                User(
                    clinic_id=clinic.id,
                    name="Seat Head",
                    email=head_email,
                    password_hash=hash_password(TEST_PASSWORD),
                    role="head_doctor",
                    is_active=True,
                ),
                User(
                    clinic_id=None,
                    name="Seat Super",
                    email=super_email,
                    password_hash=hash_password(TEST_PASSWORD),
                    role="super_admin",
                    is_active=True,
                ),
            ]
        )
        db.session.commit()
        clinic_id = clinic.id

        try:
            with app.test_client() as head:
                res = head.post("/api/auth/login", json={"email": head_email, "password": TEST_PASSWORD})
                assert res.status_code == 200, res.json

                # 1. Within the limit
                res = head.post("/api/staff", json=_staff_payload(suffix, "doc1", "doctor"))
                assert res.status_code == 201, res.json
                doc1_id = res.json["data"]["id"]
                res = head.post("/api/staff", json=_staff_payload(suffix, "sec1", "secretary"))
                assert res.status_code == 201, res.json
                print("PASS: Head doctor can create staff up to the plan limits.")

                # 2. Over the limit
                res = head.post("/api/staff", json=_staff_payload(suffix, "doc2", "doctor"))
                assert res.status_code == 403, res.json
                res = head.post("/api/staff", json=_staff_payload(suffix, "sec2", "secretary"))
                assert res.status_code == 403, res.json
                print("PASS: Creating staff beyond the plan limits is rejected.")

                # 3. Seat usage is reported
                res = head.get("/api/staff")
                assert res.json["seats"]["doctors"] == {"used": 1, "limit": 1}
                assert res.json["seats"]["secretaries"] == {"used": 1, "limit": 1}
                print("PASS: Staff list reports seat usage.")

                # 4. Inactive accounts do not use a seat, but reactivating one does
                res = head.patch(f"/api/staff/{doc1_id}", json={"is_active": False})
                assert res.status_code == 200, res.json
                res = head.post("/api/staff", json=_staff_payload(suffix, "doc3", "doctor"))
                assert res.status_code == 201, res.json
                res = head.patch(f"/api/staff/{doc1_id}", json={"is_active": True})
                assert res.status_code == 403, res.json
                print("PASS: Deactivated accounts free a seat; reactivation respects the limit.")

                # 5. Changing a secretary into a doctor respects the doctor limit
                sec_id = db.session.scalar(
                    db.select(User.id).where(User.email == f"sec1-{suffix}@aerodent.local")
                )
                res = head.patch(f"/api/staff/{sec_id}", json={"role": "doctor"})
                assert res.status_code == 403, res.json
                print("PASS: Role changes respect the plan limits.")

            with app.test_client() as admin:
                res = admin.post("/api/auth/login", json={"email": super_email, "password": TEST_PASSWORD})
                assert res.status_code == 200, res.json

                # 6. Super admin can raise limits, and rejects bad values
                res = admin.patch(f"/api/admin/clinics/{clinic_id}", json={"max_doctors": 3})
                assert res.status_code == 200, res.json
                assert res.json["data"]["max_doctors"] == 3
                res = admin.patch(f"/api/admin/clinics/{clinic_id}", json={"max_secretaries": -1})
                assert res.status_code == 422, res.json
                res = admin.patch(f"/api/admin/clinics/{clinic_id}", json={"max_secretaries": "abc"})
                assert res.status_code == 422, res.json
                print("PASS: Super admin can set seat limits; invalid values are rejected.")

                # 7. Blank means unlimited
                res = admin.patch(f"/api/admin/clinics/{clinic_id}", json={"max_doctors": ""})
                assert res.status_code == 200, res.json
                assert res.json["data"]["max_doctors"] is None
                print("PASS: A blank limit means unlimited.")

            with app.test_client() as head:
                head.post("/api/auth/login", json={"email": head_email, "password": TEST_PASSWORD})
                res = head.post("/api/staff", json=_staff_payload(suffix, "doc4", "doctor"))
                assert res.status_code == 201, res.json
                print("PASS: Raising the limit lets the head doctor add more staff.")

            print("\n==========================================")
            print("ALL SEAT LIMIT TESTS PASSED")
            print("==========================================")
        finally:
            from backend.routes.admin import purge_clinic_data

            purge_clinic_data(clinic_id)
            User.query.filter(User.email == super_email).delete(synchronize_session=False)
            db.session.commit()


if __name__ == "__main__":
    run_seat_limit_tests()
