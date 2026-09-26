from datetime import time
import sys
from pathlib import Path
from uuid import uuid4

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.app import app
from backend.auth.service import hash_password
from backend.extensions import db
from backend.models import Clinic, User


TEST_PASSWORD = "Correct Test Password!"


def run_auth_tests():
    suffix = uuid4().hex
    clinic_a_email = f"auth-a-{suffix}@aerodent.local"
    clinic_b_email = f"auth-b-{suffix}@aerodent.local"
    inactive_email = f"auth-inactive-{suffix}@aerodent.local"

    with app.app_context():
        clinic_a = Clinic(
            name=f"Authentication Test A {suffix}",
            currency="SYR",
            work_start=time(9, 0),
            work_end=time(18, 0),
            slot_duration=30,
        )
        clinic_b = Clinic(
            name=f"Authentication Test B {suffix}",
            currency="SYR",
            work_start=time(9, 0),
            work_end=time(18, 0),
            slot_duration=30,
        )
        db.session.add_all([clinic_a, clinic_b])
        db.session.flush()

        active_user = User(
            clinic_id=clinic_a.id,
            name="Authentication Test Doctor",
            email=clinic_a_email,
            password_hash=hash_password(TEST_PASSWORD),
            role="doctor",
            is_active=True,
        )
        other_clinic_user = User(
            clinic_id=clinic_b.id,
            name="Other Clinic Doctor",
            email=clinic_b_email,
            password_hash=hash_password(TEST_PASSWORD),
            role="doctor",
            is_active=True,
        )
        inactive_user = User(
            clinic_id=clinic_a.id,
            name="Inactive Test Doctor",
            email=inactive_email,
            password_hash=hash_password(TEST_PASSWORD),
            role="doctor",
            is_active=False,
        )
        db.session.add_all([active_user, other_clinic_user, inactive_user])
        db.session.commit()

        active_user_id = active_user.id
        clinic_a_id = clinic_a.id
        clinic_b_id = clinic_b.id

        try:
            with app.test_client() as client:
                response = client.get("/api/auth/me")
                assert response.status_code == 401
                print("PASS: /api/auth/me rejects unauthenticated requests.")

                response = client.post(
                    "/api/auth/login",
                    json={"email": clinic_a_email, "password": TEST_PASSWORD},
                )
                assert response.status_code == 200
                assert response.json["user"] == {
                    "id": active_user_id,
                    "name": "Authentication Test Doctor",
                    "email": clinic_a_email,
                    "role": "doctor",
                    "clinic_id": clinic_a_id,
                }
                with client.session_transaction() as current_session:
                    assert current_session.get("user_id") == active_user_id
                print("PASS: Valid credentials create a minimal session.")

                response = client.get(
                    "/api/auth/me",
                    query_string={"clinic_id": clinic_b_id},
                )
                assert response.status_code == 200
                assert response.json["user"]["clinic_id"] == clinic_a_id
                print("PASS: Authenticated clinic identity comes from the User record.")

                response = client.post("/api/auth/logout")
                assert response.status_code == 200
                assert client.get("/api/auth/me").status_code == 401
                print("PASS: Logout destroys the session.")

            with app.test_client() as client:
                wrong_password = client.post(
                    "/api/auth/login",
                    json={"email": clinic_a_email, "password": "wrong"},
                )
                unknown_email = client.post(
                    "/api/auth/login",
                    json={
                        "email": f"missing-{suffix}@aerodent.local",
                        "password": "wrong",
                    },
                )
                assert wrong_password.status_code == 401
                assert unknown_email.status_code == 401
                assert wrong_password.json == unknown_email.json
                assert client.get("/api/auth/me").status_code == 401
                print("PASS: Wrong and unknown credentials are generic 401 failures.")

            with app.test_client() as client:
                response = client.post(
                    "/api/auth/login",
                    json={"email": inactive_email, "password": TEST_PASSWORD},
                )
                assert response.status_code == 401
                assert client.get("/api/auth/me").status_code == 401
                print("PASS: Inactive users cannot create a session.")

            with app.test_client() as client:
                response = client.post(
                    "/api/auth/login",
                    json={"email": clinic_a_email, "password": TEST_PASSWORD},
                    headers={"Origin": "https://evil.example"},
                )
                assert response.status_code == 403
                print("PASS: Cross-origin state-changing auth requests are rejected.")
        finally:
            db.session.query(User).filter(
                User.email.in_([clinic_a_email, clinic_b_email, inactive_email])
            ).delete(synchronize_session=False)
            db.session.delete(clinic_a)
            db.session.delete(clinic_b)
            db.session.commit()


if __name__ == "__main__":
    with app.app_context():
        run_auth_tests()
    print()
    print("==========================================")
    print("ALL AUTHENTICATION TESTS PASSED")
    print("==========================================")
