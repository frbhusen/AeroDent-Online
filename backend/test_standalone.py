"""Standalone (desktop) edition: local SQLite database, first-run setup, no online-only features.

Run on its own (``python -m backend.test_standalone``): the edition and the database are chosen
through environment variables that must be set before the app is imported.
"""

import os
import sys
import tempfile
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

_workdir = tempfile.mkdtemp(prefix="aerodent-standalone-test-")
os.environ["AERODENT_EDITION"] = "standalone"
os.environ["AERODENT_ENV"] = "standalone"
os.environ["DATABASE_URL"] = f"sqlite:///{Path(_workdir, 'aerodent.db').as_posix()}"
os.environ["SECRET_KEY"] = "t" * 48

from backend.app import app  # noqa: E402
from backend.extensions import db  # noqa: E402

SETUP = {
    "clinic_name": "Local Clinic",
    "doctor_name": "Dr. Local",
    "email": "doctor@local.test",
    "password": "LocalPassword123!",
    "country": "SY",
    "currency": "SYR",
}


def run_standalone_tests():
    with app.app_context():
        db.create_all()

    with app.test_client() as client:
        # The desktop edition opens straight into the app and tells the frontend who it is
        res = client.get("/")
        assert res.status_code == 200 and b"onlineLoginForm" in res.data
        res = client.get("/js/edition.js")
        assert res.status_code == 200 and b"AERODENT_STANDALONE = true" in res.data
        print("PASS: The root opens the app and the edition flag says standalone.")

        # Online-only routes do not exist
        assert client.get("/api/admin/clinics").status_code == 404
        assert client.post("/api/trial/signup", json={}).status_code in (404, 405)
        assert client.post("/api/trial/intent", json={}).status_code in (404, 405)
        print("PASS: Platform administration and trial sign-up are not part of this edition.")

        # First-run setup
        assert client.get("/api/setup/status").get_json() == {"needed": True}
        assert len(client.get("/api/setup/countries").get_json()["data"]) > 10
        for field in ("clinic_name", "doctor_name", "email", "password"):
            bad = {**SETUP, field: ""}
            res = client.post("/api/setup", json=bad)
            assert res.status_code == 422 and res.get_json()["field"] == field, (field, res.data)
        assert client.post("/api/setup", json={**SETUP, "country": "ZZ"}).status_code == 422
        assert client.get("/api/setup/status").get_json() == {"needed": True}
        res = client.post("/api/setup", json=SETUP)
        assert res.status_code == 201 and res.get_json()["user"]["role"] == "head_doctor", res.data
        assert client.get("/api/auth/me").status_code == 200  # setup signs the doctor in
        print("PASS: First-run setup validates input, creates the clinic and signs the doctor in.")

        # The setup can only ever run once
        assert client.get("/api/setup/status").get_json() == {"needed": False}
        assert client.post("/api/setup", json={**SETUP, "email": "second@local.test"}).status_code == 409
        print("PASS: Setup refuses to run a second time.")

    with app.test_client() as client:
        # Normal sign-in, including the failed-login throttle (uses the SQLite-specific upsert)
        res = client.post("/api/auth/login", json={"email": SETUP["email"], "password": "wrong-password"})
        assert res.status_code == 401
        res = client.post("/api/auth/login", json={"email": SETUP["email"], "password": SETUP["password"]})
        assert res.status_code == 200, res.data
        print("PASS: Sign-in and failed-login throttling work on SQLite.")

        # The head-doctor workflow works end to end on the local database
        res = client.get("/api/clinic/profile")
        assert res.get_json()["data"]["country"] == "SY"
        res = client.post("/api/patients", json={"name": "Local Patient", "phone": "0944 123 456"})
        assert res.status_code == 201 and res.get_json()["data"]["phone"] == "+963944123456", res.data
        patient_id = res.get_json()["data"]["id"]
        res = client.patch("/api/settings", json={"procedure_prices": {"filling": "50"}})
        assert res.status_code == 200
        res = client.put(f"/api/patients/{patient_id}/odontogram/permanent/8", json={"condition": "filling"})
        assert res.status_code == 201 and res.get_json()["billing"]["action"] == "created", res.data
        res = client.get(f"/api/invoices?patient_id={patient_id}")
        assert res.get_json()["data"][0]["amount"] == "50.00"
        res = client.get("/api/dashboard")
        assert res.status_code == 200, res.data
        res = client.get("/api/inventory/items")
        assert res.status_code == 200, res.data
        res = client.get("/api/audit-logs")
        assert res.status_code == 200 and res.get_json()["data"], res.data
        print("PASS: Patients, billing, dashboard, inventory and the audit log work on SQLite.")

    print("\n==========================================")
    print("ALL STANDALONE EDITION TESTS PASSED")
    print("==========================================")


if __name__ == "__main__":
    run_standalone_tests()
