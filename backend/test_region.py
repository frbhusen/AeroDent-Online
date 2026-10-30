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
from backend.services.phone import normalize_phone

TEST_PASSWORD = "TestPassword123!"


def run_region_tests():
    suffix = uuid.uuid4().hex[:8]
    head_email = f"region-head-{suffix}@aerodent.local"
    secretary_email = f"region-sec-{suffix}@aerodent.local"
    super_email = f"region-super-{suffix}@aerodent.local"

    # ---- phone normalization rules (pure function)
    expected = {
        ("0944 123 456", "SY"): "+963944123456",
        ("944123456", "SY"): "+963944123456",
        ("00963944123456", "SY"): "+963944123456",
        ("+963 (0) 944 123 456", "SY"): "+963944123456",
        ("+9630944123456", "SY"): "+963944123456",
        ("963944123456", "SY"): "+963944123456",
        ("01001234567", "EG"): "+201001234567",
        ("+20 100 123 4567", "EG"): "+201001234567",
        ("050 123 4567", "SA"): "+966501234567",
        ("0944123456", None): "0944123456",  # no country: kept as typed
        ("00963944123456", None): "+963944123456",
    }
    for (raw, country), want in expected.items():
        got, error = normalize_phone(raw, country)
        assert error is None and got == want, (raw, country, got, error)
    assert normalize_phone("", "SY") == (None, None)
    for bad in ("abc", "12", "+963 12", "0944-xyz"):
        assert normalize_phone(bad, "SY")[1] is not None, bad
    print("PASS: Phone numbers are normalized to international format per country.")

    with app.app_context():
        clinic = Clinic(name=f"Region Clinic {suffix}", currency="SYR", is_active=True, subscription_status="active")
        db.session.add(clinic)
        db.session.flush()
        db.session.add_all(
            [
                User(clinic_id=clinic.id, name="Head", email=head_email, role="head_doctor", is_active=True,
                     password_hash=hash_password(TEST_PASSWORD)),
                User(clinic_id=clinic.id, name="Sec", email=secretary_email, role="secretary", is_active=True,
                     password_hash=hash_password(TEST_PASSWORD)),
                User(clinic_id=None, name="Super", email=super_email, role="super_admin", is_active=True,
                     password_hash=hash_password(TEST_PASSWORD)),
            ]
        )
        db.session.commit()
        clinic_id = clinic.id
        created_clinic_ids = [clinic_id]

        try:
            with app.test_client() as head:
                assert head.post("/api/auth/login", json={"email": head_email, "password": TEST_PASSWORD}).status_code == 200

                # Without a country, numbers are stored as typed
                res = head.post("/api/patients", json={"name": "No Country", "phone": "0944 123 456"})
                assert res.status_code == 201 and res.json["data"]["phone"] == "0944 123 456", res.json
                print("PASS: Clinics without a country keep phone numbers as typed.")

                # Country list and profile
                res = head.get("/api/countries")
                assert res.status_code == 200
                by_code = {c["code"]: c for c in res.json["data"]}
                assert by_code["SY"]["dial"] == "963" and by_code["EG"]["dial"] == "20"
                res = head.get("/api/clinic/profile")
                assert res.json["data"]["currency"] == "SYR" and res.json["data"]["country"] is None
                print("PASS: Countries and the clinic profile are served.")

                # Head doctor picks a country and a custom currency
                res = head.patch("/api/settings", json={"country": "SY", "currency": "ل.س", "phone": "011 123 4567"})
                assert res.status_code == 200, res.json
                assert res.json["data"]["country"] == "SY" and res.json["data"]["currency"] == "ل.س"
                assert res.json["data"]["phone"] == "+963111234567", res.json["data"]["phone"]
                assert head.get("/api/clinic/profile").json["data"]["currency"] == "ل.س"
                for bad in ({"country": "ZZ"}, {"currency": ""}, {"currency": "x" * 11}):
                    assert head.patch("/api/settings", json=bad).status_code == 422, bad
                print("PASS: Head doctor can set the country and a custom currency; phone is normalized.")

                # Patients are saved in international format
                res = head.post("/api/patients", json={"name": "Local Number", "phone": "0944 555 666"})
                assert res.status_code == 201 and res.json["data"]["phone"] == "+963944555666", res.json
                patient_id = res.json["data"]["id"]
                res = head.patch(f"/api/patients/{patient_id}", json={"phone": "00963 988 111 222"})
                assert res.json["data"]["phone"] == "+963988111222"
                res = head.post("/api/patients", json={"name": "Bad Number", "phone": "abc"})
                assert res.status_code == 422, res.json
                print("PASS: Patient phone numbers are saved in international format.")

                # Searching with the local format still finds them
                res = head.get("/api/patients?q=0944 555")
                assert any(p["id"] == patient_id for p in res.json["data"]) is False  # 0944 555 != 988...
                res = head.get("/api/patients?q=0988 111")
                assert any(p["id"] == patient_id for p in res.json["data"]), res.json
                res = head.get("/api/patients?q=%2B963988")
                assert any(p["id"] == patient_id for p in res.json["data"]), res.json
                print("PASS: Patients can be found by local or international phone format.")

            with app.test_client() as sec:
                sec.post("/api/auth/login", json={"email": secretary_email, "password": TEST_PASSWORD})
                res = sec.get("/api/clinic/profile")
                assert res.status_code == 200 and res.json["data"]["currency"] == "ل.س"
                assert sec.patch("/api/settings", json={"country": "EG"}).status_code == 403
                print("PASS: Every role can read the profile; only the head doctor can change it.")

            with app.test_client() as admin:
                assert admin.post("/api/auth/login", json={"email": super_email, "password": TEST_PASSWORD}).status_code == 200
                res = admin.post(
                    "/api/admin/clinics",
                    json={
                        "name": f"Admin Clinic {suffix}",
                        "country": "EG",
                        "currency": "EGP",
                        "phone": "010 0123 4567",
                        "head_doctor_name": "Admin Head",
                        "head_doctor_email": f"admin-head-{suffix}@aerodent.local",
                        "head_doctor_password": TEST_PASSWORD,
                    },
                )
                assert res.status_code == 201, res.json
                new_id = res.json["data"]["id"]
                created_clinic_ids.append(new_id)
                assert res.json["data"]["country"] == "EG" and res.json["data"]["phone"] == "+201001234567"
                res = admin.patch(f"/api/admin/clinics/{new_id}", json={"currency": "Ł", "country": "SA", "phone": "0501234567"})
                assert res.status_code == 200, res.json
                assert res.json["data"]["currency"] == "Ł" and res.json["data"]["phone"] == "+966501234567"
                assert admin.patch(f"/api/admin/clinics/{new_id}", json={"country": "ZZ"}).status_code == 422
                assert admin.patch(f"/api/admin/clinics/{new_id}", json={"currency": " "}).status_code == 422
                print("PASS: Super admin can set the country and a custom currency; phone is normalized.")

            # Existing numbers can be converted in one go (dry run first)
            from backend.models import Patient

            runner = app.test_cli_runner()
            legacy_id = db.session.scalar(
                db.select(Patient.id).where(Patient.clinic_id == clinic_id, Patient.name == "No Country")
            )
            assert db.session.get(Patient, legacy_id).phone == "0944 123 456"
            result = runner.invoke(args=["phones", "normalize", "--clinic-id", str(clinic_id)])
            assert result.exit_code == 0 and "dry run" in result.output and "+963944123456" in result.output, result.output
            db.session.expire_all()
            assert db.session.get(Patient, legacy_id).phone == "0944 123 456"
            result = runner.invoke(args=["phones", "normalize", "--clinic-id", str(clinic_id), "--apply"])
            assert result.exit_code == 0 and "applied" in result.output, result.output
            db.session.expire_all()
            assert db.session.get(Patient, legacy_id).phone == "+963944123456"
            print("PASS: The phones normalize command converts existing numbers (dry run by default).")

            print("\n==========================================")
            print("ALL REGION TESTS PASSED")
            print("==========================================")
        finally:
            from backend.routes.admin import purge_clinic_data

            db.session.rollback()
            for cid in created_clinic_ids:
                purge_clinic_data(cid)
            User.query.filter(User.email == super_email).delete(synchronize_session=False)
            db.session.commit()


if __name__ == "__main__":
    run_region_tests()
