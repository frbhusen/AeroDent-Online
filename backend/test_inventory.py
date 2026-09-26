import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import json
import threading
from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

from backend.app import app
from backend.auth.service import hash_password
from backend.extensions import db
from backend.models import (
    AuditLog,
    Clinic,
    InventoryBatch,
    InventoryItem,
    InventoryMovement,
    Patient,
    User,
)


PASSWORD = "InventoryPass123!"


def _login(client, email):
    res = client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    assert res.status_code == 200, f"Login failed for {email}: {res.data}"


def _logout(client):
    client.post("/api/auth/logout")


def _new_user(clinic_id, role, suffix):
    return User(
        clinic_id=clinic_id,
        name=f"Inventory {role}",
        email=f"inventory-{role}-{clinic_id}-{suffix}@aerodent.test",
        password_hash=hash_password(PASSWORD),
        role=role,
        is_active=True,
    )


def _movement(client, item_id, **payload):
    return client.post(f"/api/inventory/items/{item_id}/movements", json=payload)


def _item(client, item_id):
    res = client.get(f"/api/inventory/items/{item_id}")
    assert res.status_code == 200, res.data
    return res.json["data"]


def _assert_ledger_consistent(item_id):
    """item.quantity == sum(batches) for tracked items, and == sum(movements) always."""
    db.session.expire_all()
    item = db.session.get(InventoryItem, item_id)
    movement_total = db.session.scalar(
        db.select(db.func.coalesce(db.func.sum(InventoryMovement.quantity), 0)).where(
            InventoryMovement.item_id == item_id
        )
    )
    assert Decimal(movement_total) == item.quantity, (
        f"Ledger mismatch for item {item_id}: movements={movement_total} item={item.quantity}"
    )
    if item.track_batches:
        batch_total = db.session.scalar(
            db.select(db.func.coalesce(db.func.sum(InventoryBatch.quantity), 0)).where(
                InventoryBatch.item_id == item_id
            )
        )
        assert Decimal(batch_total) == item.quantity, (
            f"Batch mismatch for item {item_id}: batches={batch_total} item={item.quantity}"
        )
    last = db.session.scalar(
        db.select(InventoryMovement)
        .where(InventoryMovement.item_id == item_id)
        .order_by(InventoryMovement.id.desc())
    )
    if last is not None:
        assert last.quantity_after == item.quantity


def run_inventory_tests():
    suffix = uuid4().hex[:8]
    clinic_a_id = None
    clinic_b_id = None

    ctx = app.app_context()
    ctx.push()
    try:
        clinic_a = Clinic(name=f"Inventory Clinic A {suffix}", currency="USD")
        clinic_b = Clinic(name=f"Inventory Clinic B {suffix}", currency="USD")
        db.session.add_all([clinic_a, clinic_b])
        db.session.commit()
        clinic_a_id, clinic_b_id = clinic_a.id, clinic_b.id

        head_a = _new_user(clinic_a.id, "head_doctor", suffix)
        doctor_a = _new_user(clinic_a.id, "doctor", suffix)
        secretary_a = _new_user(clinic_a.id, "secretary", suffix)
        head_b = _new_user(clinic_b.id, "head_doctor", suffix)
        db.session.add_all([head_a, doctor_a, secretary_a, head_b])
        db.session.commit()

        patient_a = Patient(clinic_id=clinic_a.id, name="Inventory Patient A", created_by=head_a.id)
        patient_b = Patient(clinic_id=clinic_b.id, name="Inventory Patient B", created_by=head_b.id)
        db.session.add_all([patient_a, patient_b])
        db.session.commit()

        client = app.test_client()
        today = date.today()

        # =================================================================
        # 1. Categories & suppliers (head doctor)
        # =================================================================
        _login(client, head_a.email)

        res = client.post("/api/inventory/categories/defaults", json={"language": "en"})
        assert res.status_code == 201, res.data
        assert len(res.json["data"]) == 13
        res = client.post("/api/inventory/categories/defaults", json={"language": "en"})
        assert res.status_code == 201 and res.json["data"] == [], "Default categories must be idempotent"

        categories = client.get("/api/inventory/categories").json["data"]
        restorative = next(c for c in categories if c["name"] == "Restorative Materials")
        anesthesia = next(c for c in categories if c["name"] == "Anesthesia")

        res = client.post("/api/inventory/categories", json={"name": "restorative materials"})
        assert res.status_code == 409, "Category names must be unique case-insensitively"

        res = client.post("/api/inventory/categories", json={"name": "Temporary"})
        assert res.status_code == 201
        temp_category_id = res.json["data"]["id"]
        res = client.patch(f"/api/inventory/categories/{temp_category_id}", json={"name": "Temporary Materials"})
        assert res.status_code == 200 and res.json["data"]["name"] == "Temporary Materials"
        assert client.delete(f"/api/inventory/categories/{temp_category_id}").status_code == 204
        print("PASS: Categories create, rename, delete, defaults and uniqueness.")

        res = client.post("/api/inventory/suppliers", json={
            "name": "Dental Depot",
            "contact_person": "Sami",
            "phone": "+963 11 000 0000",
            "email": "orders@depot.test",
        })
        assert res.status_code == 201, res.data
        supplier_id = res.json["data"]["id"]
        res = client.post("/api/inventory/suppliers", json={"name": "Bad", "email": "not-an-email"})
        assert res.status_code == 422
        res = client.get("/api/inventory/suppliers?q=depot")
        assert [s["id"] for s in res.json["data"]] == [supplier_id]
        print("PASS: Supplier create, validation, and search.")

        # =================================================================
        # 2. Items: creation, opening balance, server-controlled fields
        # =================================================================
        res = client.post("/api/inventory/items", json={
            "name": "Composite A2 Syringe",
            "sku": "COMP-A2",
            "category_id": restorative["id"],
            "supplier_id": supplier_id,
            "unit": "syringe",
            "minimum_quantity": 3,
            "cost_per_unit": "12.50",
            "location": "Cabinet 2",
            "initial_quantity": 10,
        })
        assert res.status_code == 201, res.data
        composite = res.json["data"]
        assert composite["quantity"] == "10"
        assert composite["stock_status"] == "ok"
        assert composite["category_name"] == "Restorative Materials"
        assert composite["estimated_value"] == "125.00"
        composite_id = composite["id"]

        opening = client.get(f"/api/inventory/items/{composite_id}/movements").json["data"]
        assert len(opening) == 1 and opening[0]["type"] == "opening" and opening[0]["quantity"] == "10"

        res = client.post("/api/inventory/items", json={"name": "Dup", "sku": "comp-a2"})
        assert res.status_code == 409, "SKU must be unique per clinic (case-insensitive)"

        for forbidden in ({"name": "X", "quantity": 5}, {"name": "X", "clinic_id": clinic_b.id}, {"name": "X", "created_by": 1}):
            res = client.post("/api/inventory/items", json=forbidden)
            assert res.status_code == 400, f"Server-controlled field accepted: {forbidden}"

        res = client.patch(f"/api/inventory/items/{composite_id}", json={"quantity": 999})
        assert res.status_code == 400, "Quantity must not be directly editable"

        res = client.post("/api/inventory/items", json={"name": "Gloves", "expiry_date": "2030-01-01"})
        assert res.status_code == 400, "Unknown fields must be rejected"

        res = client.post("/api/inventory/items", json={
            "name": "Untracked With Expiry",
            "initial_quantity": 5,
            "initial_expiry_date": "2030-01-01",
        })
        assert res.status_code == 422, "Expiry dates require batch tracking"

        res = client.post("/api/inventory/items", json={"name": "Bad min", "minimum_quantity": -1})
        assert res.status_code == 422
        res = client.post("/api/inventory/items", json={"name": "Bad qty", "initial_quantity": "1.23456"})
        assert res.status_code == 422
        res = client.post("/api/inventory/items", json={"name": "Bad qty", "initial_quantity": True})
        assert res.status_code == 422
        print("PASS: Item creation, opening balance movement, and field protection.")

        # =================================================================
        # 3. Stock math on an untracked item
        # =================================================================
        res = _movement(client, composite_id, type="stock_in", quantity=5, unit_cost="13.00",
                        supplier_id=supplier_id, reference="INV-1001")
        assert res.status_code == 201, res.data
        assert res.json["data"]["item"]["quantity"] == "15"
        assert res.json["data"]["item"]["cost_per_unit"] == "13.00", "Latest receipt cost becomes item cost"

        res = _movement(client, composite_id, type="usage", quantity=4, reason="Class II fillings",
                        reference_type="patient", reference_id=patient_a.id)
        assert res.status_code == 201, res.data
        assert res.json["data"]["item"]["quantity"] == "11"
        assert res.json["data"]["movements"][0]["reference_id"] == patient_a.id

        res = _movement(client, composite_id, type="usage", quantity=12)
        assert res.status_code == 409, "Usage greater than stock must be rejected, not clamped"
        assert _item(client, composite_id)["quantity"] == "11"

        res = _movement(client, composite_id, type="return", quantity="1.5", reason="Unused")
        assert res.status_code == 201 and res.json["data"]["item"]["quantity"] == "12.5"

        res = _movement(client, composite_id, type="adjustment", new_quantity=12)
        assert res.status_code == 422, "Adjustments require a reason"
        res = _movement(client, composite_id, type="adjustment", new_quantity=12, reason="Monthly count")
        assert res.status_code == 201 and res.json["data"]["movements"][0]["quantity"] == "-0.5"
        res = _movement(client, composite_id, type="adjustment", quantity=-20, reason="Oops")
        assert res.status_code == 409, "Adjustment below zero must be rejected"
        res = _movement(client, composite_id, type="adjustment", new_quantity=12, reason="No-op")
        assert res.status_code == 422

        res = _movement(client, composite_id, type="damaged", quantity=2, reason="Cap cracked")
        assert res.status_code == 201 and res.json["data"]["item"]["quantity"] == "10"

        res = _movement(client, composite_id, type="usage", quantity=8)
        assert res.status_code == 201
        item = _item(client, composite_id)
        assert item["quantity"] == "2" and item["stock_status"] == "low"
        res = _movement(client, composite_id, type="usage", quantity=2)
        assert _item(client, composite_id)["stock_status"] == "out"

        # Patient reference from another clinic is rejected
        _movement(client, composite_id, type="stock_in", quantity=1)
        res = _movement(client, composite_id, type="usage", quantity=1,
                        reference_type="patient", reference_id=patient_b.id)
        assert res.status_code == 404, "Cross-clinic patient reference must be rejected"
        res = _movement(client, composite_id, type="usage", quantity=1, supplier_id=supplier_id)
        assert res.status_code == 422, "Receiving-only fields are rejected on usage"
        res = _movement(client, composite_id, type="opening", quantity=1)
        assert res.status_code == 422, "Opening movements cannot be posted directly"
        _assert_ledger_consistent(composite_id)
        print("PASS: Untracked stock math: receive, use, return, adjust, write-off, no negatives.")

        # =================================================================
        # 4. Batch tracking, FEFO usage, and expiry
        # =================================================================
        res = client.post("/api/inventory/items", json={
            "name": "Lidocaine 2% Carpule",
            "category_id": anesthesia["id"],
            "unit": "carpule",
            "minimum_quantity": 20,
            "track_batches": True,
            "initial_quantity": 10,
            "initial_batch_number": "OLD-1",
            "initial_expiry_date": (today - timedelta(days=5)).isoformat(),
            "cost_per_unit": "1.00",
        })
        assert res.status_code == 201, res.data
        lido = res.json["data"]
        lido_id = lido["id"]
        assert lido["quantity"] == "10" and lido["usable_quantity"] == "0"
        assert lido["stock_status"] == "out", "Expired stock must not count as usable"
        assert lido["expiry_status"] == "expired"

        res = _movement(client, lido_id, type="usage", quantity=1)
        assert res.status_code == 409, "Expired stock must not be usable"

        res = _movement(client, lido_id, type="stock_in", quantity=30, batch_number="LATE-3",
                        expiry_date=(today + timedelta(days=400)).isoformat(), unit_cost="1.20")
        assert res.status_code == 201
        res = _movement(client, lido_id, type="stock_in", quantity=20, batch_number="SOON-2",
                        expiry_date=(today + timedelta(days=10)).isoformat(), unit_cost="1.10")
        assert res.status_code == 201
        res = _movement(client, lido_id, type="stock_in", quantity=5, batch_number="soon-2")
        assert res.status_code == 201, "Receiving into an existing batch number adds to it"
        res = _movement(client, lido_id, type="stock_in", quantity=5, batch_number="SOON-2",
                        expiry_date=(today + timedelta(days=99)).isoformat())
        assert res.status_code == 409, "Same batch number with a different expiry is rejected"

        detail = _item(client, lido_id)
        assert detail["quantity"] == "65" and detail["usable_quantity"] == "55"
        assert detail["expiry_status"] == "expired"
        batches = {b["batch_number"]: b for b in detail["batches"]}
        assert batches["SOON-2"]["quantity"] == "25"
        assert batches["SOON-2"]["expiry_status"] == "expiring_soon"
        assert batches["OLD-1"]["expiry_status"] == "expired"

        # FEFO: 30 units should drain SOON-2 (25) then 5 from LATE-3, never touching OLD-1.
        res = _movement(client, lido_id, type="usage", quantity=30, reason="Extraction day")
        assert res.status_code == 201, res.data
        used = res.json["data"]["movements"]
        assert [(m["batch_number"], m["quantity"]) for m in used] == [("SOON-2", "-25"), ("LATE-3", "-5")]
        assert used[-1]["quantity_after"] == "35"

        res = _movement(client, lido_id, type="usage", quantity=26)
        assert res.status_code == 409, "Usage exceeding usable (non-expired) stock is rejected"

        old_batch_id = batches["OLD-1"]["id"]
        res = _movement(client, lido_id, type="usage", quantity=1, batch_id=old_batch_id)
        assert res.status_code == 409, "Using an explicitly selected expired batch is rejected"

        res = _movement(client, lido_id, type="expired", quantity=10, reason="Expired lot disposal")
        assert res.status_code == 201
        assert res.json["data"]["movements"][0]["batch_id"] == old_batch_id
        detail = _item(client, lido_id)
        assert detail["quantity"] == "25" and detail["usable_quantity"] == "25"
        assert detail["expiry_status"] == "ok"

        late_batch_id = next(b["id"] for b in detail["batches"] if b["batch_number"] == "LATE-3")
        res = _movement(client, lido_id, type="adjustment", new_quantity=24, reason="Count")
        assert res.status_code == 422, "Tracked items must be adjusted per batch"
        res = _movement(client, lido_id, type="adjustment", new_quantity=24, reason="Count", batch_id=late_batch_id)
        assert res.status_code == 201 and res.json["data"]["item"]["quantity"] == "24"
        res = _movement(client, lido_id, type="return", quantity=1)
        assert res.status_code == 422, "Tracked returns require a batch"
        res = _movement(client, lido_id, type="return", quantity=1, batch_id=late_batch_id)
        assert res.status_code == 201 and res.json["data"]["item"]["quantity"] == "25"

        res = client.patch(f"/api/inventory/items/{lido_id}", json={"track_batches": False})
        assert res.status_code == 409, "Batch tracking cannot be toggled while stock exists"
        _assert_ledger_consistent(lido_id)

        expiring = client.get("/api/inventory/batches?expiry_status=all").json["data"]
        assert all(b["item_id"] == lido_id for b in expiring)
        print("PASS: Batch tracking, FEFO consumption, expired stock unusable, per-batch adjustments.")

        # =================================================================
        # 5. Search, filtering, pagination
        # =================================================================
        client.post("/api/inventory/items", json={"name": "Nitrile Gloves M", "barcode": "5901234123457",
                                                  "minimum_quantity": 2, "initial_quantity": 100})
        res = client.get("/api/inventory/items?q=5901234")
        assert [i["name"] for i in res.json["data"]] == ["Nitrile Gloves M"]
        res = client.get("/api/inventory/items?q=comp-a")
        assert [i["id"] for i in res.json["data"]] == [composite_id]
        res = client.get(f"/api/inventory/items?category_id={anesthesia['id']}")
        assert [i["id"] for i in res.json["data"]] == [lido_id]
        res = client.get("/api/inventory/items?stock_status=low")
        assert [i["id"] for i in res.json["data"]] == [composite_id]
        res = client.get("/api/inventory/items?stock_status=ok")
        assert {i["id"] for i in res.json["data"]} == {lido_id, client.get("/api/inventory/items?q=Nitrile").json["data"][0]["id"]}
        res = client.get("/api/inventory/items?per_page=1&page=2&sort=name")
        assert res.json["meta"]["total"] == 3 and res.json["meta"]["pages"] == 3 and len(res.json["data"]) == 1
        assert client.get("/api/inventory/items?stock_status=bogus").status_code == 400
        print("PASS: Server-side search, filters, and pagination.")

        # =================================================================
        # 6. Dashboard aggregates
        # =================================================================
        dash = client.get("/api/inventory/dashboard").json["data"]
        assert dash["total_items"] == 3
        assert dash["low_stock"] == 1 and dash["out_of_stock"] == 0 and dash["in_stock"] == 2
        assert dash["expiring_soon"] == 0 and dash["expired"] == 0
        # composite: 1 x 13.00 ; lidocaine LATE-3: 25 x 1.20 ; gloves uncosted
        assert dash["estimated_value"] == "43.00", dash["estimated_value"]
        assert dash["items_without_cost"] == 1
        assert dash["receipts_last_30_days"]["count"] >= 4
        assert len(dash["recent_movements"]) == 10
        print("PASS: Dashboard aggregates computed server-side.")

        # =================================================================
        # 7. Deactivation, append-only history
        # =================================================================
        gloves_id = client.get("/api/inventory/items?q=Nitrile").json["data"][0]["id"]
        res = client.delete(f"/api/inventory/items/{gloves_id}")
        assert res.status_code == 200 and res.json["data"]["is_active"] is False
        assert _movement(client, gloves_id, type="usage", quantity=1).status_code == 409
        assert client.get("/api/inventory/items").json["meta"]["total"] == 2
        assert client.get("/api/inventory/items?active=false").json["meta"]["total"] == 1
        res = client.patch(f"/api/inventory/items/{gloves_id}", json={"is_active": True})
        assert res.status_code == 200 and res.json["data"]["is_active"] is True

        res = client.delete(f"/api/inventory/categories/{restorative['id']}")
        assert res.status_code == 409, "Categories in use must not be deleted"
        res = client.patch(f"/api/inventory/categories/{restorative['id']}", json={"is_active": False})
        assert res.status_code == 200
        res = client.post("/api/inventory/items", json={"name": "New", "category_id": restorative["id"]})
        assert res.status_code == 422, "Inactive categories cannot be assigned to new items"
        assert _item(client, composite_id)["category_name"] == "Restorative Materials"
        assert client.delete(f"/api/inventory/suppliers/{supplier_id}").status_code == 409

        movement = db.session.scalar(db.select(InventoryMovement).where(InventoryMovement.item_id == composite_id))
        movement.quantity = Decimal("999")
        try:
            db.session.flush()
        except ValueError:
            db.session.rollback()
        else:
            raise AssertionError("Inventory movements must be append-only")
        assert client.patch(f"/api/inventory/movements/{movement.id}", json={}).status_code in (404, 405)
        print("PASS: Soft deactivation, category/supplier protection, append-only movements.")

        # =================================================================
        # 8. Audit logging
        # =================================================================
        actions = set(db.session.scalars(
            db.select(AuditLog.action).where(AuditLog.clinic_id == clinic_a.id)
        ))
        for expected in (
            "inventory_item_created",
            "inventory_item_deactivated",
            "inventory_stock_received",
            "inventory_stock_used",
            "inventory_stock_adjusted",
            "inventory_stock_returned",
            "inventory_stock_written_off",
            "inventory_category_created",
            "inventory_supplier_created",
        ):
            assert expected in actions, f"Missing audit action {expected}"
        used_log = db.session.scalar(
            db.select(AuditLog).where(AuditLog.clinic_id == clinic_a.id, AuditLog.action == "inventory_stock_used")
        )
        assert "Inventory Patient" not in (used_log.details or ""), "Audit must not copy patient data"
        json.loads(used_log.details)
        print("PASS: Inventory actions are audit-logged.")
        _logout(client)

        # =================================================================
        # 9. Role-based access
        # =================================================================
        _login(client, doctor_a.email)
        assert client.get("/api/inventory/items").status_code == 200
        assert _movement(client, composite_id, type="usage", quantity=1).status_code == 201
        assert _movement(client, composite_id, type="stock_in", quantity=3).status_code == 201
        assert _movement(client, composite_id, type="adjustment", new_quantity=0, reason="x").status_code == 403
        assert _movement(client, composite_id, type="expired", quantity=1).status_code == 403
        assert client.post("/api/inventory/items", json={"name": "Nope"}).status_code == 403
        assert client.patch(f"/api/inventory/items/{composite_id}", json={"name": "Nope"}).status_code == 403
        assert client.delete(f"/api/inventory/items/{composite_id}").status_code == 403
        assert client.post("/api/inventory/categories", json={"name": "Nope"}).status_code == 403
        assert client.post("/api/inventory/suppliers", json={"name": "Nope"}).status_code == 403
        _logout(client)

        _login(client, secretary_a.email)
        assert client.get("/api/inventory/dashboard").status_code == 200
        assert _movement(client, composite_id, type="stock_in", quantity=1).status_code == 201
        assert _movement(client, composite_id, type="usage", quantity=1).status_code == 201
        assert _movement(client, composite_id, type="adjustment", new_quantity=0, reason="x").status_code == 403
        assert client.post("/api/inventory/items", json={"name": "Nope"}).status_code == 403
        assert client.post("/api/inventory/categories", json={"name": "Nope"}).status_code == 403
        res = client.post("/api/inventory/suppliers", json={"name": "Secretary Supplier"})
        assert res.status_code == 201, "Secretaries manage supplier contacts"
        _logout(client)
        _assert_ledger_consistent(composite_id)
        print("PASS: Inventory permission matrix enforced server-side.")

        # =================================================================
        # 10. Tenant isolation
        # =================================================================
        _login(client, head_b.email)
        assert client.get("/api/inventory/items").json["meta"]["total"] == 0
        assert client.get("/api/inventory/categories").json["data"] == []
        assert client.get("/api/inventory/suppliers").json["data"] == []
        assert client.get("/api/inventory/movements").json["meta"]["total"] == 0
        assert client.get("/api/inventory/batches?expiry_status=all").json["meta"]["total"] == 0
        dash_b = client.get("/api/inventory/dashboard").json["data"]
        assert dash_b["total_items"] == 0 and dash_b["recent_movements"] == []

        assert client.get(f"/api/inventory/items/{composite_id}").status_code == 404
        assert client.get(f"/api/inventory/items/{composite_id}/movements").status_code == 404
        assert client.patch(f"/api/inventory/items/{composite_id}", json={"name": "Hacked"}).status_code == 404
        assert client.delete(f"/api/inventory/items/{composite_id}").status_code == 404
        assert _movement(client, composite_id, type="stock_in", quantity=1).status_code == 404
        assert client.patch(f"/api/inventory/categories/{anesthesia['id']}", json={"name": "X"}).status_code == 404
        assert client.delete(f"/api/inventory/categories/{anesthesia['id']}").status_code == 404
        assert client.patch(f"/api/inventory/suppliers/{supplier_id}", json={"name": "X"}).status_code == 404

        # Clinic B cannot attach Clinic A's category/supplier/batch to its own records
        res = client.post("/api/inventory/items", json={"name": "B item", "category_id": anesthesia["id"]})
        assert res.status_code == 404
        res = client.post("/api/inventory/items", json={"name": "B item", "supplier_id": supplier_id})
        assert res.status_code == 404
        res = client.post("/api/inventory/items", json={"name": "B tracked", "track_batches": True, "initial_quantity": 2,
                                                        "initial_batch_number": "B1"})
        b_item_id = res.json["data"]["id"]
        res = _movement(client, b_item_id, type="usage", quantity=1, batch_id=late_batch_id)
        assert res.status_code == 404, "Batch ids from another clinic must not resolve"
        res = client.post("/api/inventory/items", json={"name": "Same SKU OK", "sku": "COMP-A2"})
        assert res.status_code == 201, "SKU uniqueness is per clinic"
        _logout(client)

        db.session.expire_all()
        assert db.session.get(InventoryItem, composite_id).name == "Composite A2 Syringe"
        print("PASS: Cross-clinic inventory access returns 404 with zero data leakage.")

        # =================================================================
        # 11. Settings: expiry warning window
        # =================================================================
        _login(client, head_a.email)
        res = client.patch("/api/settings", json={"inventory_expiry_warning_days": 500})
        assert res.status_code == 422
        res = client.patch("/api/settings", json={"inventory_expiry_warning_days": 400})
        assert res.status_code == 422
        res = client.patch("/api/settings", json={"inventory_expiry_warning_days": 365})
        assert res.status_code == 200
        lido_detail = _item(client, lido_id)
        assert lido_detail["expiry_status"] == "ok"  # LATE-3 expires in 400 days
        client.patch("/api/settings", json={"inventory_expiry_warning_days": 90})
        export = client.get("/api/clinic/export").json["data"]
        assert len(export["inventory"]["items"]) == 3
        assert len(export["inventory"]["movements"]) > 10
        _logout(client)
        print("PASS: Configurable expiry window and inventory export.")

        # =================================================================
        # 12. Concurrent usage cannot oversell stock (row lock)
        # =================================================================
        _login(client, head_a.email)
        race_item_id = client.post(
            "/api/inventory/items", json={"name": "Race Item", "initial_quantity": 10}
        ).json["data"]["id"]
        _logout(client)
        statuses = []

        def _worker():
            with app.app_context():
                worker_client = app.test_client()
                _login(worker_client, head_a.email)
                for _ in range(3):
                    statuses.append(_movement(worker_client, race_item_id, type="usage", quantity=1).status_code)

        threads = [threading.Thread(target=_worker) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        assert statuses.count(201) == 10 and statuses.count(409) == 14, statuses
        _assert_ledger_consistent(race_item_id)
        assert db.session.get(InventoryItem, race_item_id).quantity == 0
        print("PASS: Concurrent usage serialized; stock never oversold.")

    finally:
        db.session.rollback()
        from backend.routes.admin import purge_clinic_data
        if clinic_a_id:
            purge_clinic_data(clinic_a_id)
        if clinic_b_id:
            purge_clinic_data(clinic_b_id)
        db.session.commit()
        ctx.pop()

    print("\n================================================================")
    print("ALL INVENTORY TESTS PASSED")
    print("================================================================\n")


if __name__ == "__main__":
    run_inventory_tests()
