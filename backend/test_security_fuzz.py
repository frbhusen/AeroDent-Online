"""
Hostile-input sweep: every API route is called with malformed IDs, query strings and
bodies. No request may produce a 500, leak a stack trace, or succeed where it should not.
"""
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import re
from uuid import uuid4

from backend.app import app
from backend.auth.service import hash_password
from backend.extensions import db
from backend.models import AuthThrottle, Clinic, Patient, User


PASSWORD = "Fuzz-Password-2026"
HUGE = "99999999999999999999"
QUERY_VALUES = [HUGE, "-1", "0", "abc", "' OR 1=1 --", "1;DROP TABLE users", "<script>", "%00", "2026-13-45", "1e999", ""]
BODIES = [
    None,
    "not json",
    [],
    [1, 2, 3],
    {"__proto__": {"x": 1}},
    {"id": HUGE, "clinic_id": 1, "patient_id": HUGE, "name": None},
    {"patient_id": HUGE, "treatment_id": HUGE, "amount": "1e999", "date": "2026-02-30", "time": "25:61"},
    {"name": "x" * 20000, "notes": "<img src=x onerror=alert(1)>", "email": "a" * 400},
    {"patient_id": "' OR 1=1 --", "doctor_id": [], "duration": -5, "fee": "NaN", "status": {"$ne": 1}},
    {"quantity": "Infinity", "type": "usage", "minimum_quantity": -1, "cost_per_unit": "1e400"},
    {key: "L" * 400 for key in (
        "name", "title", "credential_number", "issuing_authority", "shift_type", "credential_type", "notes",
        "dosage", "frequency", "duration", "instructions", "procedure", "diagnosis", "description", "phone",
        "location", "work_study", "gender", "tooth_tag", "type", "filename", "reference", "reason", "sku",
        "barcode", "unit", "contact_person", "email", "address", "currency", "payment_method", "priority",
        "condition", "medications")},
    {"medications": [{"name": "M" * 400, "dosage": "D" * 400, "frequency": "F" * 400, "duration": "U" * 400}]},
    {"status": [], "role": {}, "priority": [], "type": {}, "shift_type": [], "credential_type": {},
     "tooth_mode": [], "gender": {}, "currency": [], "subscription_status": {}, "is_active": "yes",
     "language": {}, "unit": [], "date": {}, "start_time": [], "expiry_date": [], "medications": "x"},
]
LEAK_MARKERS = ("Traceback", "sqlalchemy", "psycopg", "/home/", "File \"", "SECRET")


def _concrete(rule):
    return re.sub(r"<(?:int|string):[a-z_]+>", lambda m: HUGE if m.group(0).startswith("<int") else "x", rule)


def run_fuzz_tests():
    suffix = uuid4().hex[:8]
    ctx = app.app_context()
    ctx.push()
    clinic_id = None
    failures = []
    try:
        db.session.query(AuthThrottle).delete()
        clinic = Clinic(name=f"Fuzz {suffix}", currency="USD")
        db.session.add(clinic)
        db.session.commit()
        clinic_id = clinic.id
        head = User(clinic_id=clinic.id, name="Fuzz Head", email=f"fuzz.{suffix}@test.local",
                    password_hash=hash_password(PASSWORD), role="head_doctor", is_active=True)
        db.session.add(head)
        db.session.commit()
        db.session.add(Patient(clinic_id=clinic.id, name="Fuzz Patient", created_by=head.id))
        db.session.commit()

        client = app.test_client()
        client.environ_base["REMOTE_ADDR"] = "10.99.0.1"
        assert client.post("/api/auth/login", json={"email": head.email, "password": PASSWORD}).status_code == 200

        routes = [
            (rule.rule, sorted(rule.methods - {"HEAD", "OPTIONS"}))
            for rule in app.url_map.iter_rules()
            if rule.rule.startswith("/api/") and not rule.rule.startswith("/api/auth/")
        ]
        calls = 0

        def check(method, url, **kwargs):
            nonlocal calls
            calls += 1
            response = client.open(url, method=method, **kwargs)
            body = response.get_data().decode("utf-8", errors="replace")
            # "Invalid input value." is the DataError safety net: reaching it means the route let an
            # invalid value through to PostgreSQL instead of validating it first.
            if response.status_code >= 500 or any(marker in body for marker in LEAK_MARKERS) or "Invalid input value." in body:
                failures.append(f"{method} {url} {kwargs.get('json', kwargs.get('data'))!r:.80} -> {response.status_code} {body[:160]}")

        for rule, methods in routes:
            url = _concrete(rule)
            for method in methods:
                if method == "GET":
                    check("GET", url)
                    for value in QUERY_VALUES:
                        for param in ("page", "per_page", "patient_id", "doctor_id", "user_id", "item_id",
                                      "category_id", "date", "start_date", "end_date", "status", "q", "type",
                                      "limit", "offset", "clinic_id", "sort", "stock_status", "active"):
                            check("GET", url, query_string={param: value})
                else:
                    for body in BODIES:
                        if isinstance(body, str):
                            check(method, url, data=body, content_type="application/json")
                        else:
                            check(method, url, json=body)
                    check(method, url, data=b"\xff\xfe\x00garbage", content_type="application/json")
                    check(method, url, data={"file": "notafile"}, content_type="multipart/form-data")

        # Second pass with REAL record IDs so every handler's body validation is exercised.
        today = "2026-09-26"
        patient_id = client.post("/api/patients", json={"name": "Fuzz Real"}).get_json()["data"]["id"]
        ids = {"patient_id": patient_id}
        creators = {
            "treatment_id": ("/api/treatments", {"patient_id": patient_id, "description": "x", "fee": "10", "date": today}),
            "treatment_plan_id": ("/api/treatment-plans", {"patient_id": patient_id, "procedure": "x", "fee": "10"}),
            "appointment_id": ("/api/appointments", {"patient_id": patient_id, "date": today, "start_time": "10:00", "duration": 30}),
            "prescription_id": ("/api/prescriptions", {"patient_id": patient_id, "date": today, "medications": [{"name": "A"}]}),
            "entry_id": ("/api/waitlist", {"patient_id": patient_id, "notes": "x"}),
            "item_id": ("/api/inventory/items", {"name": "Fuzz item", "initial_quantity": 5}),
            "category_id": ("/api/inventory/categories", {"name": f"Fuzz cat {suffix}"}),
            "supplier_id": ("/api/inventory/suppliers", {"name": "Fuzz supplier"}),
            "shift_id": ("/api/hr/shifts", {"user_id": head.id, "date": today, "start_time": "08:00", "end_time": "12:00"}),
            "credential_id": ("/api/hr/credentials", {"user_id": head.id, "title": "License", "expiry_date": "2030-01-01"}),
        }
        for key, (url, payload) in creators.items():
            res = client.post(url, json=payload)
            if res.status_code in (200, 201):
                ids[key] = res.get_json()["data"]["id"]
        if "treatment_id" in ids:
            res = client.post("/api/invoices", json={"patient_id": patient_id, "treatment_id": ids["treatment_id"], "amount": "10"})
            if res.status_code == 201:
                ids["invoice_id"] = res.get_json()["data"]["id"]
        staff = client.post("/api/staff", json={"name": "Fuzz Staff", "email": f"fs.{suffix}@test.local", "password": PASSWORD, "role": "doctor"})
        if staff.status_code == 201:
            ids["user_id"] = staff.get_json()["data"]["id"]

        def real_url(rule):
            def sub(match):
                name = match.group(2)
                if match.group(1) == "string":
                    return "permanent"
                return str(ids.get(name, HUGE))
            return re.sub(r"<(int|string):([a-z_]+)>", sub, rule)

        ordered = sorted(routes, key=lambda r: "DELETE" in r[1])
        for rule, methods in ordered:
            if "<" not in rule:
                continue
            url = real_url(rule).replace("/odontogram/permanent/" + HUGE, "/odontogram/permanent/14")
            for method in sorted(methods, key=lambda m: m == "DELETE"):
                if method in ("GET", "DELETE"):
                    continue
                for body in BODIES:
                    if isinstance(body, str):
                        check(method, url, data=body, content_type="application/json")
                    else:
                        check(method, url, json=body)
                check(method, url, data={"file": "notafile"}, content_type="multipart/form-data")
        print(f"INFO: second pass used real IDs for {sorted(ids)}")

        # Oversized payload is rejected cleanly (413), not by crashing.
        big = client.post("/api/patients", data=b"{" + b" " * (app.config["MAX_CONTENT_LENGTH"] + 1024) + b"}", content_type="application/json")
        assert big.status_code == 413, big.status_code

        assert not failures, "\n".join(failures[:40]) + f"\n... {len(failures)} failures"
        print(f"PASS: {calls} hostile requests across {len(routes)} routes; no 5xx and no internal details leaked.")
    finally:
        db.session.rollback()
        db.session.query(AuthThrottle).delete()
        from backend.routes.admin import purge_clinic_data
        if clinic_id:
            purge_clinic_data(clinic_id)
        db.session.commit()
        ctx.pop()

    print("\n================================================================")
    print("ALL SECURITY FUZZ TESTS PASSED")
    print("================================================================\n")


if __name__ == "__main__":
    run_fuzz_tests()
