import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from datetime import time
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from PIL import Image

from backend.app import app
from backend.auth.service import hash_password
from backend.extensions import db
from backend.models import Clinic, Patient, User, XRay
from backend.services.storage import LocalFileStorage


TEST_PASSWORD = "Correct XRay Password!"


def image_bytes(image_format="PNG"):
    output = BytesIO()
    Image.new("RGB", (4, 4), "red").save(output, format=image_format)
    return output.getvalue()


def create_user(clinic_id, role, suffix):
    return User(
        clinic_id=clinic_id,
        name=f"{role} {suffix}",
        email=f"xray-{role}-{suffix}@aerodent.local",
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


def upload(client, patient_id, filename="../unsafe.png", **fields):
    data = {"file": (BytesIO(image_bytes()), filename)}
    data.update(fields)
    return client.post(
        f"/api/patients/{patient_id}/x-rays",
        data=data,
        content_type="multipart/form-data",
    )


def run_xray_tests():
    suffix = uuid4().hex
    with TemporaryDirectory() as storage_root:
        app.config["AERODENT_STORAGE_PATH"] = storage_root
        with app.app_context():
            clinic_a = Clinic(
                name=f"XRay Test A {suffix}",
                currency="SYR",
                work_start=time(9, 0),
                work_end=time(18, 0),
                slot_duration=30,
            )
            clinic_b = Clinic(
                name=f"XRay Test B {suffix}",
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
            db.session.commit()

            patient_a_id = patient_a.id
            patient_b_id = patient_b.id
            clinic_a_id = clinic_a.id
            try:
                with app.test_client() as client:
                    assert client.get("/api/x-rays/1").status_code == 401
                    assert client.get("/api/x-rays/1/file").status_code == 401
                    assert client.get(f"/api/patients/{patient_a_id}/x-rays").status_code == 401
                    assert upload(client, patient_a_id).status_code == 401
                    print("PASS: Unauthenticated X-ray operations return 401.")

                with app.test_client() as client:
                    login(client, secretary_a)
                    assert client.get(f"/api/patients/{patient_a_id}/x-rays").status_code == 200
                    assert upload(client, patient_a_id).status_code == 403
                    print("PASS: Secretary can read but cannot upload X-rays.")

                with app.test_client() as client:
                    login(client, doctor_a)
                    response = upload(
                        client,
                        patient_a_id,
                        filename="../unsafe image.png",
                        tooth_tag="14",
                        type="bitewing",
                        date="2026-09-20",
                        time="10:30",
                        notes="Clinical image",
                    )
                    assert response.status_code == 201
                    xray_id = response.json["data"]["id"]
                    xray = db.session.get(XRay, xray_id)
                    assert xray.clinic_id == clinic_a_id
                    assert xray.patient_id == patient_a_id
                    assert xray.uploaded_by == doctor_a.id
                    assert xray.mime_type == "image/png"
                    assert xray.original_mime_type == "image/png"
                    assert "unsafe" in xray.filename and ".." not in xray.filename
                    assert xray.storage_key is None, "new X-rays must not depend on filesystem storage"
                    assert xray.image is not None and xray.image.encoding in ("original", "png-lossless")
                    assert not any(Path(storage_root).rglob("*")), "nothing may be written to disk"
                    print("PASS: Valid images are stored in the database, losslessly, with safe filenames.")

                    response = client.get(f"/api/patients/{patient_a_id}/x-rays")
                    assert response.status_code == 200
                    assert response.json["meta"]["count"] == 1
                    assert "storage_key" not in response.json["data"][0]
                    response = client.get(f"/api/x-rays/{xray_id}")
                    assert response.status_code == 200
                    assert "storage_key" not in response.json["data"]
                    response = client.get(f"/api/x-rays/{xray_id}/file")
                    assert response.status_code == 200
                    assert response.content_type == "image/png"
                    assert "no-store" in response.headers["Cache-Control"] and "private" in response.headers["Cache-Control"]
                    assert response.data[:8] == b"\x89PNG\r\n\x1a\n"
                    print("PASS: Metadata and protected file retrieval work without path leakage.")

                    response = client.patch(
                        f"/api/x-rays/{xray_id}",
                        json={"tooth_tag": "15", "notes": "Updated"},
                    )
                    assert response.status_code == 200
                    updated = db.session.get(XRay, xray_id)
                    assert updated.tooth_tag == "15"
                    assert updated.notes == "Updated"
                    assert updated.patient_id == patient_a_id
                    assert updated.uploaded_by == doctor_a.id
                    print("PASS: Doctor can update metadata only.")

                    oversized_notes_res = client.patch(
                        f"/api/x-rays/{xray_id}",
                        json={"notes": "x" * 2001},
                    )
                    assert oversized_notes_res.status_code == 422, (
                        f"Expected 422, got {oversized_notes_res.status_code}"
                    )
                    oversized_tag_res = client.patch(
                        f"/api/x-rays/{xray_id}",
                        json={"tooth_tag": "x" * 101},
                    )
                    assert oversized_tag_res.status_code == 422, (
                        f"Expected 422, got {oversized_tag_res.status_code}"
                    )
                    unchanged = db.session.get(XRay, xray_id)
                    assert unchanged.notes == "Updated"
                    print("PASS: Oversized X-ray metadata fields are rejected.")

                    assert client.patch(
                        f"/api/x-rays/{xray_id}",
                        json={"storage_key": "../../secret.txt"},
                    ).status_code == 400
                    assert client.delete(f"/api/x-rays/{xray_id}").status_code == 204
                    assert db.session.get(XRay, xray_id) is None
                    print("PASS: X-ray deletion removes metadata and private file safely.")

                with app.test_client() as client:
                    login(client, doctor_a)
                    invalid = client.post(
                        f"/api/patients/{patient_a_id}/x-rays",
                        data={"file": (BytesIO(b"not an image"), "fake.webp")},
                        content_type="multipart/form-data",
                    )
                    assert invalid.status_code == 422
                    spoofed = client.post(
                        f"/api/patients/{patient_a_id}/x-rays",
                        data={"file": (BytesIO(b"not an image"), "fake.webp")},
                        content_type="multipart/form-data",
                        headers={"Content-Type": "multipart/form-data; boundary=unused"},
                    )
                    assert spoofed.status_code in {400, 422}
                    missing = client.post(
                        f"/api/patients/{patient_a_id}/x-rays",
                        data={},
                        content_type="multipart/form-data",
                    )
                    assert missing.status_code == 400
                    oversized = client.post(
                        f"/api/patients/{patient_a_id}/x-rays",
                        data={"file": (BytesIO(b"x" * (app.config["XRAY_MAX_UPLOAD_BYTES"] + 1)), "large.png")},
                        content_type="multipart/form-data",
                    )
                    assert oversized.status_code == 413
                    print("PASS: Missing, spoofed, non-image, and oversized files are rejected.")

                    assert upload(client, patient_b_id).status_code == 404
                    print("PASS: Cross-clinic patient upload is blocked.")

                with app.test_client() as client:
                    login(client, doctor_b)
                    response = upload(client, patient_b_id, filename="clinic-b.png")
                    assert response.status_code == 201
                    clinic_b_xray_id = response.json["data"]["id"]

                with app.test_client() as client:
                    login(client, doctor_a)
                    assert client.get(f"/api/x-rays/{clinic_b_xray_id}").status_code == 404
                    assert client.get(f"/api/x-rays/{clinic_b_xray_id}/file").status_code == 404
                    assert client.patch(
                        f"/api/x-rays/{clinic_b_xray_id}", json={"notes": "nope"}
                    ).status_code == 404
                    assert client.delete(f"/api/x-rays/{clinic_b_xray_id}").status_code == 404
                    print("PASS: Cross-clinic metadata and file access are blocked.")

                with app.test_client() as client:
                    login(client, head_a)
                    response = upload(client, patient_a_id, filename="head.png")
                    assert response.status_code == 201
                    head_xray_id = response.json["data"]["id"]
                    assert client.patch(
                        f"/api/x-rays/{head_xray_id}",
                        json={"type": "panoramic"},
                    ).status_code == 200
                    assert client.delete(f"/api/x-rays/{head_xray_id}").status_code == 204
                    print("PASS: Head doctor has full X-ray access.")
            finally:
                db.session.delete(clinic_a)
                db.session.delete(clinic_b)
                db.session.commit()


if __name__ == "__main__":
    run_xray_tests()
    print()
    print("==========================================")
    print("ALL X-RAY API TESTS PASSED")
    print("==========================================")
