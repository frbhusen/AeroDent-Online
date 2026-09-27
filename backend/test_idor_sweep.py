"""
Object-level authorization sweep: a head doctor of clinic B tries every API route and method
against record IDs that belong to clinic A. Every attempt must be refused (404/403), and
clinic A's data must be unchanged afterwards.
"""
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import io
import re
from uuid import uuid4

from PIL import Image

from backend.app import app
from backend.services.clinic_backup import load_backup_bytes
from backend.auth.service import hash_password
from backend.extensions import db
from backend.models import AuthThrottle, Clinic, User


PASSWORD = "Idor-Sweep-Password-1"
TODAY = "2026-09-26"


def _png():
    out = io.BytesIO()
    Image.new("L", (8, 8), 128).save(out, format="PNG")
    return out.getvalue()


def _login(client, email):
    res = client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    assert res.status_code == 200, res.data


def run_idor_sweep():
    suffix = uuid4().hex[:8]
    ctx = app.app_context()
    ctx.push()
    clinic_ids = []
    try:
        db.session.query(AuthThrottle).delete()
        clinics = [Clinic(name=f"IDOR {n} {suffix}", currency="USD") for n in ("A", "B")]
        db.session.add_all(clinics)
        db.session.commit()
        clinic_ids = [c.id for c in clinics]
        heads = []
        for clinic, n in zip(clinics, ("a", "b")):
            user = User(clinic_id=clinic.id, name=f"Head {n}", email=f"idor.{n}.{suffix}@test.local",
                        password_hash=hash_password(PASSWORD), role="head_doctor", is_active=True)
            db.session.add(user)
            heads.append(user)
        db.session.commit()

        a = app.test_client()
        a.environ_base["REMOTE_ADDR"] = "10.60.0.1"
        _login(a, heads[0].email)

        pid = a.post("/api/patients", json={"name": "Clinic A Patient"}).get_json()["data"]["id"]
        ids = {"patient_id": pid}

        def create(key, url, payload, **kwargs):
            res = a.post(url, json=payload, **kwargs) if payload is not None else a.post(url, **kwargs)
            assert res.status_code in (200, 201), (url, res.status_code, res.data)
            body = res.get_json()
            ids[key] = (body.get("data") or body.get("payment"))["id"]

        create("treatment_id", "/api/treatments", {"patient_id": pid, "description": "Filling", "fee": "10", "date": TODAY})
        create("treatment_plan_id", "/api/treatment-plans", {"patient_id": pid, "procedure": "Crown", "fee": "10"})
        create("appointment_id", "/api/appointments", {"patient_id": pid, "date": TODAY, "start_time": "10:00", "duration": 30})
        create("prescription_id", "/api/prescriptions", {"patient_id": pid, "date": TODAY, "medications": [{"name": "Amoxicillin"}]})
        create("invoice_id", "/api/invoices", {"patient_id": pid, "treatment_id": ids["treatment_id"], "amount": "10"})
        create("payment_id", f"/api/invoices/{ids['invoice_id']}/payments", {"amount": "1"})
        create("entry_id", "/api/waitlist", {"patient_id": pid, "notes": "x"})
        create("item_id", "/api/inventory/items", {"name": "A glove", "initial_quantity": 5})
        create("category_id", "/api/inventory/categories", {"name": f"A cat {suffix}"})
        create("supplier_id", "/api/inventory/suppliers", {"name": "A supplier"})
        create("shift_id", "/api/hr/shifts", {"user_id": heads[0].id, "date": TODAY, "start_time": "08:00", "end_time": "12:00"})
        create("credential_id", "/api/hr/credentials", {"user_id": heads[0].id, "title": "License", "expiry_date": "2030-01-01"})
        create("user_id", "/api/staff", {"name": "A Staff", "email": f"idor.staff.{suffix}@test.local", "password": PASSWORD, "role": "doctor"})
        create("xray_id", f"/api/patients/{pid}/x-rays", None,
               data={"file": (io.BytesIO(_png()), "a.png"), "type": "bitewing"}, content_type="multipart/form-data")
        a.put(f"/api/patients/{pid}/odontogram/permanent/14", json={"condition": "decay"})

        snapshot_before = load_backup_bytes(a.get("/api/clinic/export").data)[1]["tables"]

        b = app.test_client()
        b.environ_base["REMOTE_ADDR"] = "10.60.0.2"
        _login(b, heads[1].email)

        routes = [
            (rule.rule, sorted(rule.methods - {"HEAD", "OPTIONS"}))
            for rule in app.url_map.iter_rules()
            if rule.rule.startswith("/api/") and "<" in rule.rule
            and not rule.rule.startswith("/api/admin/")
        ]
        attempts, leaks = 0, []
        bodies = {"PATCH": {"name": "Hijacked", "notes": "Hijacked", "status": "cancelled"},
                  "PUT": {"condition": "extract", "notes": "Hijacked"},
                  "POST": {"amount": "1", "type": "usage", "quantity": 1}}
        for rule, methods in routes:
            url = re.sub(r"<string:[a-z_]+>", "permanent",
                         re.sub(r"<int:([a-z_]+)>", lambda m: str(ids.get(m.group(1), 0)), rule))
            url = url.replace("/odontogram/permanent/0", "/odontogram/permanent/14")
            for method in sorted(methods, key=lambda m: m == "DELETE"):
                attempts += 1
                kwargs = {"json": bodies.get(method)} if method in bodies else {}
                if "x-rays" in url and method == "POST":
                    kwargs = {"data": {"file": (io.BytesIO(_png()), "b.png")}, "content_type": "multipart/form-data"}
                res = b.open(url, method=method, **kwargs)
                missing_url = re.sub(r"/\d+(?=/|$)", "/2147483000", url).replace("/odontogram/permanent/2147483000", "/odontogram/permanent/14")
                if "x-rays" in missing_url and method == "POST":
                    kwargs = {"data": {"file": (io.BytesIO(_png()), "b.png")}, "content_type": "multipart/form-data"}
                control = b.open(missing_url, method=method, **kwargs)
                same_as_missing = (res.status_code, res.get_data()) == (control.status_code, control.get_data())
                if res.status_code < 400 or res.status_code >= 500 or not same_as_missing:
                    leaks.append(f"{method} {url} -> {res.status_code} {res.get_data(as_text=True)[:100]} | missing-id control -> {control.status_code}")

        assert not leaks, "\n".join(leaks)
        snapshot_after = load_backup_bytes(a.get("/api/clinic/export").data)[1]["tables"]
        for key, rows in snapshot_before.items():
            assert rows == snapshot_after[key], f"clinic A {key} changed"
        exported_b = load_backup_bytes(b.get("/api/clinic/export").data)[1]["tables"]
        assert all(rows == [] for rows in exported_b.values()), {k: len(v) for k, v in exported_b.items() if v}
        print(f"PASS: {attempts} cross-clinic attempts on {len(routes)} object routes were refused, each indistinguishable from a non-existent ID; clinic A data unchanged.")

        # A secretary cannot use clinical write routes even inside their own clinic.
        sec = User(clinic_id=clinics[0].id, name="Sec", email=f"idor.sec.{suffix}@test.local",
                   password_hash=hash_password(PASSWORD), role="secretary", is_active=True)
        db.session.add(sec)
        db.session.commit()
        s = app.test_client()
        s.environ_base["REMOTE_ADDR"] = "10.60.0.3"
        _login(s, sec.email)
        forbidden = [
            ("PATCH", f"/api/treatments/{ids['treatment_id']}", {"fee": "0"}),
            ("DELETE", f"/api/prescriptions/{ids['prescription_id']}", None),
            ("DELETE", f"/api/x-rays/{ids['xray_id']}", None),
            ("PUT", f"/api/patients/{pid}/odontogram/permanent/14", {"condition": "extract"}),
            ("GET", "/api/staff", None),
            ("PATCH", "/api/settings", {"name": "x"}),
            ("GET", "/api/clinic/export", None),
            ("GET", "/api/audit-logs", None),
            ("POST", "/api/hr/shifts", {"user_id": sec.id, "date": TODAY, "start_time": "08:00", "end_time": "09:00"}),
            ("DELETE", f"/api/inventory/items/{ids['item_id']}", None),
            ("POST", f"/api/inventory/items/{ids['item_id']}/movements", {"type": "adjustment", "new_quantity": 0, "reason": "x"}),
            ("GET", "/api/admin/clinics", None),
        ]
        for method, url, body in forbidden:
            res = s.open(url, method=method, json=body) if body is not None else s.open(url, method=method)
            assert res.status_code == 403, (method, url, res.status_code, res.data)
        print(f"PASS: {len(forbidden)} role-restricted operations are refused for a secretary.")

        anon = app.test_client()
        for rule, methods in routes[:40]:
            url = re.sub(r"<[a-z]+:[a-z_]+>", "1", rule)
            for method in methods:
                assert anon.open(url, method=method).status_code in (401, 403, 404), (method, url)
        print("PASS: Unauthenticated requests to object routes are refused.")
    finally:
        db.session.rollback()
        db.session.query(AuthThrottle).delete()
        from backend.routes.admin import purge_clinic_data
        for cid in clinic_ids:
            purge_clinic_data(cid)
        db.session.commit()
        ctx.pop()

    print("\n================================================================")
    print("ALL IDOR / RBAC SWEEP TESTS PASSED")
    print("================================================================\n")


if __name__ == "__main__":
    run_idor_sweep()
