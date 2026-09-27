"""
X-ray storage guarantees: database-backed, lossless, integrity-checked, atomic, private.
"""
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import os
import random
import tempfile
from io import BytesIO
from uuid import uuid4

from PIL import Image

from backend.app import app
from backend.services.clinic_backup import load_backup_bytes
from backend.auth.service import hash_password
from backend.extensions import db
from backend.models import AuthThrottle, Clinic, Patient, User, XRay, XRayImage
from backend.services.xray_images import pixel_sha256


PASSWORD = "Xray-Storage-Password-1"


def _encode(image, fmt, **kwargs):
    out = BytesIO()
    image.save(out, format=fmt, **kwargs)
    return out.getvalue()


def _radiograph(width, height, mode="I;16", seed=7):
    """Synthetic radiograph: smooth anatomy-like gradients plus fine sensor noise."""
    rng = random.Random(seed)
    if mode == "I;16":
        img = Image.new("I", (width, height))
        img.putdata([
            min(65535, int(20000 + 30000 * ((x * y) % 997) / 997 + rng.randint(0, 900)))
            for y in range(height) for x in range(width)
        ])
        return img.convert("I;16")
    img = Image.new("L", (width, height))
    img.putdata([min(255, (x + 2 * y) % 220 + rng.randint(0, 20)) for y in range(height) for x in range(width)])
    return img if mode == "L" else img.convert(mode)


def _upload(client, patient_id, content, filename):
    return client.post(
        f"/api/patients/{patient_id}/x-rays",
        data={"file": (BytesIO(content), filename), "type": "panoramic"},
        content_type="multipart/form-data",
    )


def _download(client, xray_id):
    res = client.get(f"/api/x-rays/{xray_id}/file?download=1")
    assert res.status_code == 200, res.data
    return res


def run_xray_storage_tests():
    suffix = uuid4().hex[:8]
    ctx = app.app_context()
    ctx.push()
    clinic_ids = []
    try:
        db.session.query(AuthThrottle).delete()
        clinic, other = Clinic(name=f"XS {suffix}", currency="USD"), Clinic(name=f"XS other {suffix}", currency="USD")
        db.session.add_all([clinic, other])
        db.session.commit()
        clinic_ids = [clinic.id, other.id]
        doctor = User(clinic_id=clinic.id, name="Dr X", email=f"xs.doc.{suffix}@t.local", password_hash=hash_password(PASSWORD), role="doctor", is_active=True)
        secretary = User(clinic_id=clinic.id, name="Sec X", email=f"xs.sec.{suffix}@t.local", password_hash=hash_password(PASSWORD), role="secretary", is_active=True)
        outsider = User(clinic_id=other.id, name="Out", email=f"xs.out.{suffix}@t.local", password_hash=hash_password(PASSWORD), role="head_doctor", is_active=True)
        db.session.add_all([doctor, secretary, outsider])
        db.session.commit()
        patient = Patient(clinic_id=clinic.id, name="Radiograph Patient", created_by=doctor.id)
        db.session.add(patient)
        db.session.commit()

        client = app.test_client()
        client.environ_base["REMOTE_ADDR"] = "10.70.0.1"
        assert client.post("/api/auth/login", json={"email": doctor.email, "password": PASSWORD}).status_code == 200

        # ------------------------------------------------------------------ lossless
        cases = {
            "16-bit TIFF (uncompressed panoramic)": (_radiograph(900, 450, "I;16"), "TIFF", {}, "xr.tif", "png-lossless"),
            "8-bit BMP": (_radiograph(640, 480, "L"), "BMP", {}, "xr.bmp", "png-lossless"),
            "uncompressed PNG": (_radiograph(640, 480, "L"), "PNG", {"compress_level": 0}, "xr.png", "png-lossless"),
            "RGB PNG": (_radiograph(320, 240, "RGB"), "PNG", {"compress_level": 1}, "xr-rgb.png", "png-lossless"),
            "JPEG": (_radiograph(640, 480, "L"), "JPEG", {"quality": 95}, "xr.jpg", "original"),
            "WebP": (_radiograph(320, 240, "RGB"), "WEBP", {"lossless": True}, "xr.webp", "original"),
            "CMYK TIFF": (_radiograph(200, 100, "RGB").convert("CMYK"), "TIFF", {}, "xr-cmyk.tif", "original"),
        }
        uploaded = {}
        for label, (image, fmt, kwargs, name, expected_encoding) in cases.items():
            content = _encode(image, fmt, **kwargs)
            res = _upload(client, patient.id, content, name)
            assert res.status_code == 201, (label, res.data)
            data = res.get_json()["data"]
            meta = data["image"]
            assert meta["encoding"] == expected_encoding, (label, meta)
            assert meta["lossless"] is True
            assert (meta["width"], meta["height"]) == image.size, f"{label}: resolution changed"
            downloaded = _download(client, data["id"]).data
            with Image.open(BytesIO(content)) as original, Image.open(BytesIO(downloaded)) as stored:
                original.load(); stored.load()
                assert pixel_sha256(original) == pixel_sha256(stored), f"{label}: pixels changed"
            if expected_encoding == "original":
                assert downloaded == content, f"{label}: original bytes were not preserved"
            else:
                assert len(downloaded) < len(content), f"{label}: lossless re-encoding must be smaller"
            uploaded[label] = (data["id"], content, downloaded)
        print(f"PASS: {len(cases)} formats stored losslessly: pixels verified identical, resolution untouched.")

        tif_id = uploaded["16-bit TIFF (uncompressed panoramic)"][0]
        with Image.open(BytesIO(uploaded["16-bit TIFF (uncompressed panoramic)"][2])) as stored16:
            assert stored16.mode in ("I;16", "I") and stored16.getextrema()[1] > 255, "16-bit depth must be preserved"
        print("PASS: 16-bit radiograph depth preserved (no reduction to 8-bit).")

        # A PNG that is already optimally compressed is kept byte-for-byte.
        noisy = Image.frombytes("L", (256, 256), os.urandom(256 * 256))
        best_png = _encode(noisy, "PNG", optimize=True, compress_level=9)
        res = _upload(client, patient.id, best_png, "noise.png")
        assert res.get_json()["data"]["image"]["encoding"] == "original"
        assert _download(client, res.get_json()["data"]["id"]).data == best_png
        print("PASS: Re-encoding is skipped when it would not reduce size; original bytes kept.")

        # Formats browsers cannot show get a display preview; download still returns the original.
        cmyk_id, cmyk_bytes, _ = uploaded["CMYK TIFF"]
        inline = client.get(f"/api/x-rays/{cmyk_id}/file")
        assert inline.status_code == 200 and inline.content_type == "image/png"
        assert _download(client, cmyk_id).data == cmyk_bytes
        print("PASS: Non-browser formats display via a preview; download returns the preserved original.")

        # ------------------------------------------------------------------ source-file independence
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as handle:
            handle.write(_encode(_radiograph(300, 200, "L"), "PNG"))
            source_path = handle.name
        with open(source_path, "rb") as handle:
            source_bytes = handle.read()
        res = _upload(client, patient.id, source_bytes, "from-disk.png")
        independent_id = res.get_json()["data"]["id"]
        os.remove(source_path)
        assert not os.path.exists(source_path)
        client.post("/api/auth/logout")
        assert client.post("/api/auth/login", json={"email": doctor.email, "password": PASSWORD}).status_code == 200
        with Image.open(BytesIO(source_bytes)) as a, Image.open(BytesIO(_download(client, independent_id).data)) as b:
            assert pixel_sha256(a) == pixel_sha256(b)
        print("PASS: Deleting the source file on the device has no effect; image served after re-login.")

        # ------------------------------------------------------------------ access control
        other_session = app.test_client()
        other_session.environ_base["REMOTE_ADDR"] = "10.70.0.2"
        assert other_session.post("/api/auth/login", json={"email": secretary.email, "password": PASSWORD}).status_code == 200
        assert other_session.get(f"/api/x-rays/{independent_id}/file").status_code == 200
        outsider_session = app.test_client()
        outsider_session.environ_base["REMOTE_ADDR"] = "10.70.0.3"
        assert outsider_session.post("/api/auth/login", json={"email": outsider.email, "password": PASSWORD}).status_code == 200
        for path in ("file", "file?download=1", "verify", ""):
            assert outsider_session.get(f"/api/x-rays/{independent_id}/{path}".rstrip("/")).status_code == 404
        assert app.test_client().get(f"/api/x-rays/{independent_id}/file").status_code == 401
        headers = _download(client, independent_id).headers
        assert "no-store" in headers["Cache-Control"] and headers["X-Content-Type-Options"] == "nosniff"
        assert "sandbox" in headers["Content-Security-Policy"] and headers["Content-Disposition"].startswith("attachment")
        print("PASS: Same-clinic sessions can view; other clinics get 404; anonymous 401; responses private & sandboxed.")

        # ------------------------------------------------------------------ malicious uploads
        bomb = Image.new("L", (1, 1))
        bomb_png = _encode(bomb, "PNG")
        # Patch IHDR to claim a 60000 x 60000 image (3.6 gigapixels) without a matching CRC fix
        # so decoders must refuse it before allocating memory.
        huge = bytearray(bomb_png)
        huge[16:24] = (60000).to_bytes(4, "big") * 2
        for payload, name in [
            (bytes(huge), "bomb.png"),
            (b"GIF89a" + b"\x00" * 20, "truncated.gif"),
            (b"%PDF-1.4 not an image", "doc.png"),
            (b"<svg xmlns='http://www.w3.org/2000/svg' onload='alert(1)'/>", "evil.svg"),
            (_encode(_radiograph(64, 64, "L"), "PNG")[:200], "cut.png"),
        ]:
            res = _upload(client, patient.id, payload, name)
            assert res.status_code in (413, 422), (name, res.status_code, res.data)
        jpeg_named_png = _encode(_radiograph(64, 64, "L"), "JPEG")
        res = _upload(client, patient.id, jpeg_named_png, "misleading.png")
        assert res.status_code == 201 and res.get_json()["data"]["image"]["format"] == "JPEG"
        assert _download(client, res.get_json()["data"]["id"]).headers["Content-Type"] == "image/jpeg"
        print("PASS: Decompression bombs, truncated/non-image/SVG payloads are rejected; type comes from content.")

        # ------------------------------------------------------------------ atomicity & consistency
        count_before = (db.session.scalar(db.select(db.func.count(XRay.id))), db.session.scalar(db.select(db.func.count(XRayImage.id))))
        _upload(client, patient.id, b"garbage", "bad.png")
        count_after = (db.session.scalar(db.select(db.func.count(XRay.id))), db.session.scalar(db.select(db.func.count(XRayImage.id))))
        assert count_before == count_after, "a failed upload must not leave records behind"
        orphans = db.session.scalar(db.text(
            "SELECT count(*) FROM x_rays x LEFT JOIN xray_images i ON i.xray_id = x.id "
            "WHERE i.id IS NULL AND x.storage_key IS NULL"))
        assert orphans == 0, "every database-backed X-ray must have its image"
        assert client.delete(f"/api/x-rays/{independent_id}").status_code == 204
        assert db.session.scalar(db.select(db.func.count(XRayImage.id)).where(XRayImage.xray_id == independent_id)) == 0
        print("PASS: Failed uploads leave nothing; deleting an X-ray deletes its image in the same transaction.")

        # ------------------------------------------------------------------ integrity
        target_id = uploaded["JPEG"][0]
        assert client.get(f"/api/x-rays/{target_id}/verify").get_json()["data"]["verified"] is True
        db.session.execute(db.text(
            "UPDATE xray_images SET data = overlay(data placing '\\x00'::bytea from 400 for 1) WHERE xray_id = :id"
        ), {"id": target_id})
        db.session.commit()
        assert client.get(f"/api/x-rays/{target_id}/file?download=1").status_code == 409
        verdict = client.get(f"/api/x-rays/{target_id}/verify").get_json()["data"]
        assert verdict["verified"] is False and "SHA-256" in verdict["reason"]
        runner = app.test_cli_runner()
        result = runner.invoke(args=["xrays", "verify"])
        assert result.exit_code == 1 and f"xray_id={target_id}" in result.output, result.output
        print("PASS: Corruption is detected (download refused with 409, verify endpoint and CLI report it).")

        # ------------------------------------------------------------------ legacy files
        with tempfile.TemporaryDirectory() as storage_root:
            previous_root = app.config["AERODENT_STORAGE_PATH"]
            app.config["AERODENT_STORAGE_PATH"] = storage_root
            try:
                legacy_bytes = _encode(_radiograph(120, 80, "RGB"), "WEBP", quality=82)
                key = f"clinics/{clinic.id}/legacy-{suffix}.webp"
                Path(storage_root, key).parent.mkdir(parents=True)
                Path(storage_root, key).write_bytes(legacy_bytes)
                legacy = XRay(clinic_id=clinic.id, patient_id=patient.id, uploaded_by=doctor.id, filename="legacy.webp",
                              storage_key=key, mime_type="image/webp", original_mime_type="image/png",
                              date=__import__("datetime").date.today())
                db.session.add(legacy)
                db.session.commit()
                assert client.get(f"/api/x-rays/{legacy.id}/file").data == legacy_bytes
                result = runner.invoke(args=["xrays", "import-legacy", "--delete-files"])
                assert "imported=1" in result.output, result.output
                db.session.expire_all()
                migrated = db.session.get(XRay, legacy.id)
                assert migrated.storage_key is None and migrated.image.encoding == "legacy-webp"
                assert not Path(storage_root, key).exists()
                assert _download(client, legacy.id).data == legacy_bytes
            finally:
                app.config["AERODENT_STORAGE_PATH"] = previous_root
        print("PASS: Legacy filesystem X-rays keep working and import byte-for-byte into the database.")

        # ------------------------------------------------------------------ export
        head = User(clinic_id=clinic.id, name="Head X", email=f"xs.head.{suffix}@t.local", password_hash=hash_password(PASSWORD), role="head_doctor", is_active=True)
        db.session.add(head)
        db.session.commit()
        head_session = app.test_client()
        head_session.environ_base["REMOTE_ADDR"] = "10.70.0.4"
        head_session.post("/api/auth/login", json={"email": head.email, "password": PASSWORD})
        manifest, exported = load_backup_bytes(head_session.get("/api/clinic/export").data)
        images = exported["tables"]["xray_images"]
        assert images and len(images) == len(exported["tables"]["x_rays"])
        corrupt = set(manifest["corrupt_images"])
        assert corrupt, "the image corrupted earlier in this test must be flagged"
        assert all(manifest["files"].get(f"xrays/{img['id']}/data") == img["sha256"] for img in images if img["id"] not in corrupt)
        print("PASS: Clinic export carries every X-ray image byte-for-byte, verified by SHA-256.")
    finally:
        db.session.rollback()
        db.session.query(AuthThrottle).delete()
        from backend.routes.admin import purge_clinic_data
        for cid in clinic_ids:
            purge_clinic_data(cid)
        db.session.commit()
        remaining = db.session.scalar(db.select(db.func.count(XRayImage.id)).where(XRayImage.clinic_id.in_(clinic_ids or [0])))
        assert remaining == 0, "purging a clinic must remove its X-ray images"
        ctx.pop()

    print("\n================================================================")
    print("ALL X-RAY STORAGE TESTS PASSED")
    print("================================================================\n")


if __name__ == "__main__":
    run_xray_storage_tests()
