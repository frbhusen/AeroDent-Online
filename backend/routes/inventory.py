from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from flask import Blueprint, g, jsonify, request
from sqlalchemy import and_, func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from backend.auth import login_required, require_permission, user_has_permission
from backend.extensions import db
from backend.models import (
    InventoryBatch,
    InventoryCategory,
    InventoryItem,
    InventoryMovement,
    InventorySupplier,
)
from backend.services.audit import log_activity
from backend.services.inventory import (
    ZERO,
    InventoryError,
    adjust_stock,
    expiry_status_for,
    expiry_window_days,
    format_money,
    format_quantity,
    item_status_columns,
    lock_item,
    parse_money,
    parse_optional_date,
    parse_quantity,
    parse_text,
    receive_stock,
    remove_stock,
    return_stock,
    scoped_batch,
    stock_status_for,
    validate_reference,
)


inventory_blueprint = Blueprint("inventory", __name__, url_prefix="/api/inventory")

DEFAULT_PER_PAGE = 25
MAX_PER_PAGE = 100

SERVER_CONTROLLED_FIELDS = frozenset({"id", "clinic_id", "created_by", "created_at", "updated_at"})

ITEM_EDITABLE_FIELDS = frozenset(
    {
        "name",
        "sku",
        "barcode",
        "category_id",
        "supplier_id",
        "description",
        "unit",
        "minimum_quantity",
        "cost_per_unit",
        "location",
        "track_batches",
    }
)
ITEM_CREATE_FIELDS = ITEM_EDITABLE_FIELDS | {
    "initial_quantity",
    "initial_batch_number",
    "initial_expiry_date",
}

SUPPLIER_FIELDS = frozenset({"name", "contact_person", "phone", "email", "address", "notes", "is_active"})

# Which permission each movement type requires. "opening" is only created alongside a new item.
MOVEMENT_PERMISSIONS = {
    "stock_in": "inventory.stock_in",
    "usage": "inventory.stock_out",
    "return": "inventory.stock_out",
    "supplier_return": "inventory.adjust",
    "expired": "inventory.adjust",
    "damaged": "inventory.adjust",
    "loss": "inventory.adjust",
    "adjustment": "inventory.adjust",
}
WRITE_OFF_TYPES = frozenset({"supplier_return", "expired", "damaged", "loss"})
MOVEMENT_AUDIT_ACTIONS = {
    "stock_in": "inventory_stock_received",
    "usage": "inventory_stock_used",
    "return": "inventory_stock_returned",
    "adjustment": "inventory_stock_adjusted",
    "supplier_return": "inventory_stock_written_off",
    "expired": "inventory_stock_written_off",
    "damaged": "inventory_stock_written_off",
    "loss": "inventory_stock_written_off",
}
MOVEMENT_FIELDS = frozenset(
    {
        "type",
        "quantity",
        "new_quantity",
        "batch_id",
        "batch_number",
        "expiry_date",
        "unit_cost",
        "supplier_id",
        "reference",
        "reason",
        "notes",
        "reference_type",
        "reference_id",
    }
)

DEFAULT_CATEGORIES = {
    "en": [
        "Restorative Materials",
        "Endodontics",
        "Orthodontics",
        "Surgery",
        "Prosthetics",
        "Anesthesia",
        "Disinfection & Sterilization",
        "PPE",
        "Medicines",
        "Instruments",
        "Equipment",
        "Office Supplies",
        "Other",
    ],
    "ar": [
        "مواد ترميمية",
        "علاج العصب",
        "تقويم الأسنان",
        "الجراحة",
        "التعويضات",
        "التخدير",
        "التعقيم والتطهير",
        "معدات الوقاية الشخصية",
        "الأدوية",
        "الأدوات",
        "الأجهزة",
        "مستلزمات مكتبية",
        "أخرى",
    ],
}


ITEM_LOAD_OPTIONS = (selectinload(InventoryItem.category), selectinload(InventoryItem.supplier))
MOVEMENT_LOAD_OPTIONS = (
    selectinload(InventoryMovement.item),
    selectinload(InventoryMovement.batch),
    selectinload(InventoryMovement.supplier),
    selectinload(InventoryMovement.creator),
)


def _error(message, status):
    return jsonify({"error": message}), status


def _json_object():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return None, _error("Request body must be a JSON object.", 400)
    return data, None


def _clinic_id():
    return g.current_user.clinic_id


def _today():
    return date.today()


def _warning_days():
    return expiry_window_days(g.current_clinic)


def _pagination():
    try:
        page = max(int(request.args.get("page", 1)), 1)
        per_page = min(max(int(request.args.get("per_page", DEFAULT_PER_PAGE)), 1), MAX_PER_PAGE)
    except ValueError:
        raise InventoryError("page and per_page must be positive integers.", 400)
    return page, per_page


def _meta(page, per_page, total):
    return {
        "page": page,
        "per_page": per_page,
        "total": total,
        "pages": (total + per_page - 1) // per_page if total else 0,
    }


def _int_arg(name):
    raw = request.args.get(name)
    if raw in (None, "", "all"):
        return None
    try:
        return int(raw)
    except ValueError:
        raise InventoryError(f"{name} must be an integer.", 400)


def _parse_bool(value, field):
    if not isinstance(value, bool):
        raise InventoryError(f"{field} must be true or false.")
    return value


def _parse_id(value, field):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise InventoryError(f"{field} must be an integer or null.")
    return value


@inventory_blueprint.errorhandler(InventoryError)
def _handle_inventory_error(err):
    db.session.rollback()
    return _error(err.message, err.status)


# ---------------------------------------------------------------------------
# Scoped lookups
# ---------------------------------------------------------------------------

def _scoped(model, resource_id):
    return db.session.scalar(
        db.select(model).where(model.id == resource_id, model.clinic_id == _clinic_id())
    )


def _assignable_category(category_id, current_id=None):
    if category_id is None:
        return None
    category = _scoped(InventoryCategory, category_id)
    if category is None:
        raise InventoryError("Category not found.", 404)
    if not category.is_active and category.id != current_id:
        raise InventoryError("This category is inactive.")
    return category


def _assignable_supplier(supplier_id, current_id=None):
    if supplier_id is None:
        return None
    supplier = _scoped(InventorySupplier, supplier_id)
    if supplier is None:
        raise InventoryError("Supplier not found.", 404)
    if not supplier.is_active and supplier.id != current_id:
        raise InventoryError("This supplier is inactive.")
    return supplier


# ---------------------------------------------------------------------------
# Serializers
# ---------------------------------------------------------------------------

def _serialize_category(category, item_count=None):
    data = {
        "id": category.id,
        "clinic_id": category.clinic_id,
        "name": category.name,
        "is_active": category.is_active,
        "created_at": category.created_at.isoformat() if category.created_at else None,
        "updated_at": category.updated_at.isoformat() if category.updated_at else None,
    }
    if item_count is not None:
        data["item_count"] = item_count
    return data


def _serialize_supplier(supplier, item_count=None):
    data = {
        "id": supplier.id,
        "clinic_id": supplier.clinic_id,
        "name": supplier.name,
        "contact_person": supplier.contact_person,
        "phone": supplier.phone,
        "email": supplier.email,
        "address": supplier.address,
        "notes": supplier.notes,
        "is_active": supplier.is_active,
        "created_at": supplier.created_at.isoformat() if supplier.created_at else None,
        "updated_at": supplier.updated_at.isoformat() if supplier.updated_at else None,
    }
    if item_count is not None:
        data["item_count"] = item_count
    return data


def _serialize_item(item, status):
    """``status`` holds the computed columns from item_status_columns for this item."""
    usable = status["usable_quantity"]
    nearest_expiry = status["nearest_expiry"]
    if status["has_expired"]:
        expiry_status = "expired"
    elif status["has_expiring"]:
        expiry_status = "expiring_soon"
    elif nearest_expiry is not None:
        expiry_status = "ok"
    else:
        expiry_status = "none"

    value = None
    if item.cost_per_unit is not None:
        value = usable * item.cost_per_unit if usable > 0 else ZERO

    return {
        "id": item.id,
        "clinic_id": item.clinic_id,
        "name": item.name,
        "sku": item.sku,
        "barcode": item.barcode,
        "category_id": item.category_id,
        "category_name": item.category.name if item.category else None,
        "supplier_id": item.supplier_id,
        "supplier_name": item.supplier.name if item.supplier else None,
        "description": item.description,
        "unit": item.unit,
        "quantity": format_quantity(item.quantity),
        "usable_quantity": format_quantity(max(usable, ZERO)),
        "expired_quantity": format_quantity(status["expired_quantity"]),
        "minimum_quantity": format_quantity(item.minimum_quantity),
        "cost_per_unit": format_money(item.cost_per_unit),
        "estimated_value": format_money(value),
        "location": item.location,
        "track_batches": item.track_batches,
        "is_active": item.is_active,
        "stock_status": stock_status_for(usable, item.minimum_quantity),
        "expiry_status": expiry_status,
        "nearest_expiry": nearest_expiry.isoformat() if nearest_expiry else None,
        "created_by": item.created_by,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
    }


def _item_status(item):
    columns = item_status_columns(_today(), _warning_days())
    row = db.session.execute(
        db.select(*[expr.label(name) for name, expr in columns.items()])
        .select_from(InventoryItem)
        .where(InventoryItem.id == item.id, InventoryItem.clinic_id == item.clinic_id)
    ).mappings().one()
    return dict(row)


def _serialize_item_fresh(item):
    db.session.flush()
    return _serialize_item(item, _item_status(item))


def _serialize_batch(batch, item=None):
    today = _today()
    data = {
        "id": batch.id,
        "item_id": batch.item_id,
        "batch_number": batch.batch_number,
        "quantity": format_quantity(batch.quantity),
        "unit_cost": format_money(batch.unit_cost),
        "expiry_date": batch.expiry_date.isoformat() if batch.expiry_date else None,
        "expiry_status": expiry_status_for(batch.expiry_date, today, _warning_days()),
        "days_to_expiry": (batch.expiry_date - today).days if batch.expiry_date else None,
        "supplier_id": batch.supplier_id,
        "supplier_name": batch.supplier.name if batch.supplier else None,
        "received_at": batch.received_at.isoformat() if batch.received_at else None,
    }
    if item is not None:
        data["item_name"] = item.name
        data["item_unit"] = item.unit
    return data


def _serialize_movement(movement):
    return {
        "id": movement.id,
        "item_id": movement.item_id,
        "item_name": movement.item.name if movement.item else None,
        "item_unit": movement.item.unit if movement.item else None,
        "batch_id": movement.batch_id,
        "batch_number": movement.batch.batch_number if movement.batch else None,
        "type": movement.type,
        "quantity": format_quantity(movement.quantity),
        "quantity_after": format_quantity(movement.quantity_after),
        "unit_cost": format_money(movement.unit_cost),
        "supplier_id": movement.supplier_id,
        "supplier_name": movement.supplier.name if movement.supplier else None,
        "reference": movement.reference,
        "reason": movement.reason,
        "notes": movement.notes,
        "reference_type": movement.reference_type,
        "reference_id": movement.reference_id,
        "created_by": movement.created_by,
        "created_by_name": movement.creator.name if movement.creator else None,
        "created_at": movement.created_at.isoformat() if movement.created_at else None,
    }


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@inventory_blueprint.get("/dashboard")
@login_required
@require_permission("inventory.read")
def inventory_dashboard():
    clinic_id = _clinic_id()
    today = _today()
    warning_days = _warning_days()
    columns = item_status_columns(today, warning_days)
    active_items = and_(InventoryItem.clinic_id == clinic_id, InventoryItem.is_active.is_(True))

    counts = db.session.execute(
        db.select(
            func.count(InventoryItem.id).label("total"),
            func.count(InventoryItem.id).filter(columns["stock_status"] == "ok").label("in_stock"),
            func.count(InventoryItem.id).filter(columns["stock_status"] == "low").label("low_stock"),
            func.count(InventoryItem.id).filter(columns["stock_status"] == "out").label("out_of_stock"),
            func.count(InventoryItem.id).filter(columns["has_expiring"]).label("expiring_soon"),
            func.count(InventoryItem.id).filter(columns["has_expired"]).label("expired"),
        ).where(active_items)
    ).mappings().one()

    # Estimated value of usable (non-expired) stock at recorded unit costs. Batch-tracked
    # stock uses each batch's received cost, falling back to the item's current cost.
    untracked_value = db.session.scalar(
        db.select(func.coalesce(func.sum(InventoryItem.quantity * InventoryItem.cost_per_unit), ZERO)).where(
            active_items,
            InventoryItem.track_batches.is_(False),
            InventoryItem.cost_per_unit.is_not(None),
        )
    )
    batch_cost = func.coalesce(InventoryBatch.unit_cost, InventoryItem.cost_per_unit)
    usable_batch = and_(
        InventoryBatch.clinic_id == InventoryItem.clinic_id,
        InventoryBatch.item_id == InventoryItem.id,
        InventoryBatch.quantity > 0,
        or_(InventoryBatch.expiry_date.is_(None), InventoryBatch.expiry_date >= today),
    )
    tracked_value = db.session.scalar(
        db.select(func.coalesce(func.sum(InventoryBatch.quantity * batch_cost), ZERO))
        .select_from(InventoryBatch)
        .join(InventoryItem, usable_batch)
        .where(active_items, InventoryItem.track_batches.is_(True), batch_cost.is_not(None))
    )
    uncosted_untracked = db.session.scalar(
        db.select(func.count(InventoryItem.id)).where(
            active_items,
            InventoryItem.track_batches.is_(False),
            InventoryItem.cost_per_unit.is_(None),
            InventoryItem.quantity > 0,
        )
    )
    uncosted_tracked = db.session.scalar(
        db.select(func.count(func.distinct(InventoryItem.id)))
        .select_from(InventoryBatch)
        .join(InventoryItem, usable_batch)
        .where(active_items, InventoryItem.track_batches.is_(True), batch_cost.is_(None))
    )

    since = datetime.now(timezone.utc) - timedelta(days=30)
    receipts = db.session.execute(
        db.select(
            func.count(InventoryMovement.id).label("count"),
            func.coalesce(
                func.sum(InventoryMovement.quantity * InventoryMovement.unit_cost), ZERO
            ).label("cost"),
        ).where(
            InventoryMovement.clinic_id == clinic_id,
            InventoryMovement.type == "stock_in",
            InventoryMovement.created_at >= since,
        )
    ).mappings().one()

    attention_rows = db.session.execute(
        db.select(InventoryItem, *[expr.label(name) for name, expr in columns.items()])
        .options(*ITEM_LOAD_OPTIONS)
        .where(active_items, columns["stock_status"] != "ok")
        .order_by(columns["usable_quantity"].asc(), InventoryItem.name.asc())
        .limit(8)
    ).all()

    expiring_batches = db.session.execute(
        db.select(InventoryBatch, InventoryItem)
        .join(
            InventoryItem,
            and_(InventoryItem.clinic_id == InventoryBatch.clinic_id, InventoryItem.id == InventoryBatch.item_id),
        )
        .where(
            active_items,
            InventoryBatch.quantity > 0,
            InventoryBatch.expiry_date.is_not(None),
            InventoryBatch.expiry_date <= today + timedelta(days=warning_days),
        )
        .order_by(InventoryBatch.expiry_date.asc(), InventoryBatch.id.asc())
        .limit(8)
    ).all()

    recent_movements = db.session.scalars(
        db.select(InventoryMovement)
        .options(*MOVEMENT_LOAD_OPTIONS)
        .where(InventoryMovement.clinic_id == clinic_id)
        .order_by(InventoryMovement.id.desc())
        .limit(10)
    ).all()

    return jsonify(
        {
            "data": {
                "total_items": counts["total"],
                "in_stock": counts["in_stock"],
                "low_stock": counts["low_stock"],
                "out_of_stock": counts["out_of_stock"],
                "expiring_soon": counts["expiring_soon"],
                "expired": counts["expired"],
                "expiry_warning_days": warning_days,
                "estimated_value": format_money(untracked_value + tracked_value),
                "items_without_cost": (uncosted_untracked or 0) + (uncosted_tracked or 0),
                "receipts_last_30_days": {
                    "count": receipts["count"],
                    "cost": format_money(receipts["cost"]),
                },
                "attention_items": [
                    _serialize_item(row[0], dict(row._mapping)) for row in attention_rows
                ],
                "expiring_batches": [
                    _serialize_batch(batch, item) for batch, item in expiring_batches
                ],
                "recent_movements": [_serialize_movement(m) for m in recent_movements],
            }
        }
    )


# ---------------------------------------------------------------------------
# Items
# ---------------------------------------------------------------------------

@inventory_blueprint.get("/items")
@login_required
@require_permission("inventory.read")
def list_items():
    clinic_id = _clinic_id()
    columns = item_status_columns(_today(), _warning_days())
    query = (
        db.select(InventoryItem, *[expr.label(name) for name, expr in columns.items()])
        .where(InventoryItem.clinic_id == clinic_id)
        .options(*ITEM_LOAD_OPTIONS)
    )

    active = request.args.get("active", "true")
    if active == "true":
        query = query.where(InventoryItem.is_active.is_(True))
    elif active == "false":
        query = query.where(InventoryItem.is_active.is_(False))
    elif active != "all":
        return _error("active must be true, false, or all.", 400)

    search = request.args.get("q", "").strip()
    if search:
        pattern = f"%{search}%"
        query = query.where(
            or_(
                InventoryItem.name.ilike(pattern),
                InventoryItem.sku.ilike(pattern),
                InventoryItem.barcode.ilike(pattern),
                InventoryItem.location.ilike(pattern),
            )
        )

    category_id = _int_arg("category_id")
    if category_id is not None:
        query = query.where(InventoryItem.category_id == category_id)

    supplier_id = _int_arg("supplier_id")
    if supplier_id is not None:
        query = query.where(InventoryItem.supplier_id == supplier_id)

    stock_status = request.args.get("stock_status", "all")
    if stock_status == "attention":
        query = query.where(columns["stock_status"] != "ok")
    elif stock_status in {"ok", "low", "out"}:
        query = query.where(columns["stock_status"] == stock_status)
    elif stock_status != "all":
        return _error("stock_status must be one of: all, ok, low, out, attention.", 400)

    expiry_status = request.args.get("expiry_status", "all")
    if expiry_status == "expired":
        query = query.where(columns["has_expired"])
    elif expiry_status == "expiring_soon":
        query = query.where(columns["has_expiring"])
    elif expiry_status == "attention":
        query = query.where(or_(columns["has_expired"], columns["has_expiring"]))
    elif expiry_status != "all":
        return _error("expiry_status must be one of: all, expired, expiring_soon, attention.", 400)

    sort = request.args.get("sort", "name")
    order_by = {
        "name": (InventoryItem.name.asc(), InventoryItem.id.asc()),
        "quantity": (columns["usable_quantity"].asc(), InventoryItem.name.asc()),
        "expiry": (columns["nearest_expiry"].asc().nulls_last(), InventoryItem.name.asc()),
        "updated": (InventoryItem.updated_at.desc(), InventoryItem.id.desc()),
    }.get(sort)
    if order_by is None:
        return _error("sort must be one of: name, quantity, expiry, updated.", 400)

    page, per_page = _pagination()
    total = db.session.scalar(db.select(func.count()).select_from(query.subquery()))
    rows = db.session.execute(
        query.order_by(*order_by).offset((page - 1) * per_page).limit(per_page)
    ).all()

    return jsonify(
        {
            "data": [_serialize_item(row[0], dict(row._mapping)) for row in rows],
            "meta": _meta(page, per_page, total),
        }
    )


@inventory_blueprint.get("/items/<int:item_id>")
@login_required
@require_permission("inventory.read")
def get_item(item_id):
    item = _scoped(InventoryItem, item_id)
    if item is None:
        return _error("Inventory item not found.", 404)

    batches = db.session.scalars(
        db.select(InventoryBatch)
        .where(
            InventoryBatch.clinic_id == item.clinic_id,
            InventoryBatch.item_id == item.id,
            InventoryBatch.quantity > 0,
        )
        .order_by(InventoryBatch.expiry_date.asc().nulls_last(), InventoryBatch.id.asc())
    ).all()
    movements = db.session.scalars(
        db.select(InventoryMovement)
        .options(*MOVEMENT_LOAD_OPTIONS)
        .where(InventoryMovement.clinic_id == item.clinic_id, InventoryMovement.item_id == item.id)
        .order_by(InventoryMovement.id.desc())
        .limit(20)
    ).all()

    data = _serialize_item(item, _item_status(item))
    data["batches"] = [_serialize_batch(b) for b in batches]
    data["recent_movements"] = [_serialize_movement(m) for m in movements]
    return jsonify({"data": data})


def _apply_item_fields(item, data, *, creating):
    if "name" in data or creating:
        item.name = parse_text(data.get("name"), "name", 200, required=True)
    if "sku" in data:
        item.sku = parse_text(data["sku"], "sku", 64)
    if "barcode" in data:
        item.barcode = parse_text(data["barcode"], "barcode", 64)
    if "description" in data:
        item.description = parse_text(data["description"], "description", 2000)
    if "unit" in data or creating:
        item.unit = parse_text(data.get("unit"), "unit", 30) or "piece"
    if "location" in data:
        item.location = parse_text(data["location"], "location", 120)
    if "minimum_quantity" in data:
        item.minimum_quantity = parse_quantity(
            data["minimum_quantity"] if data["minimum_quantity"] is not None else 0,
            "minimum_quantity",
            allow_zero=True,
        )
    elif creating:
        item.minimum_quantity = ZERO
    if "cost_per_unit" in data:
        item.cost_per_unit = parse_money(data["cost_per_unit"], "cost_per_unit")
    if "category_id" in data:
        category_id = _parse_id(data["category_id"], "category_id")
        _assignable_category(category_id, current_id=None if creating else item.category_id)
        item.category_id = category_id
    if "supplier_id" in data:
        supplier_id = _parse_id(data["supplier_id"], "supplier_id")
        _assignable_supplier(supplier_id, current_id=None if creating else item.supplier_id)
        item.supplier_id = supplier_id
    if "track_batches" in data:
        track = _parse_bool(data["track_batches"], "track_batches")
        if not creating and track != item.track_batches and item.quantity != 0:
            raise InventoryError(
                "Batch tracking can only be changed while the item has no stock. "
                "Adjust or write off the remaining stock first.",
                409,
            )
        item.track_batches = track
    elif creating:
        item.track_batches = False


@inventory_blueprint.post("/items")
@login_required
@require_permission("inventory.create")
def create_item():
    data, error = _json_object()
    if error:
        return error
    if set(data) & (SERVER_CONTROLLED_FIELDS | {"quantity"}):
        return _error(
            "Ownership fields are server-controlled; use initial_quantity to record opening stock.",
            400,
        )
    if set(data) - ITEM_CREATE_FIELDS:
        return _error("Unsupported inventory item field.", 400)

    initial_quantity = data.get("initial_quantity")
    initial_quantity = (
        parse_quantity(initial_quantity, "initial_quantity", allow_zero=True)
        if initial_quantity not in (None, "")
        else ZERO
    )
    initial_batch = parse_text(data.get("initial_batch_number"), "initial_batch_number", 64)
    initial_expiry = parse_optional_date(data.get("initial_expiry_date"), "initial_expiry_date")

    item = InventoryItem(
        clinic_id=_clinic_id(),
        created_by=g.current_user.id,
        quantity=ZERO,
        is_active=True,
    )
    _apply_item_fields(item, data, creating=True)
    if initial_quantity == 0 and (initial_batch or initial_expiry):
        raise InventoryError("initial_quantity is required when a batch number or expiry date is given.")

    db.session.add(item)
    try:
        db.session.flush()
    except IntegrityError:
        db.session.rollback()
        return _error("An item with this SKU already exists.", 409)

    if initial_quantity > 0:
        receive_stock(
            item,
            quantity=initial_quantity,
            user=g.current_user,
            movement_type="opening",
            batch_number=initial_batch,
            expiry_date=initial_expiry,
            unit_cost=item.cost_per_unit,
            supplier_id=item.supplier_id,
            reason="Opening balance",
        )

    log_activity(
        action="inventory_item_created",
        resource_type="inventory_item",
        resource_id=item.id,
        details={"name": item.name, "sku": item.sku, "initial_quantity": format_quantity(initial_quantity)},
    )
    db.session.commit()
    return jsonify({"data": _serialize_item_fresh(item)}), 201


@inventory_blueprint.patch("/items/<int:item_id>")
@login_required
@require_permission("inventory.update")
def update_item(item_id):
    data, error = _json_object()
    if error:
        return error
    if "quantity" in data:
        return _error("Stock quantity can only change through stock movements (receive, use, adjust).", 400)
    if set(data) & SERVER_CONTROLLED_FIELDS:
        return _error("Ownership fields are server-controlled.", 400)
    if set(data) - (ITEM_EDITABLE_FIELDS | {"is_active"}):
        return _error("Unsupported inventory item field.", 400)
    if not data:
        return _error("At least one field is required.", 400)

    item = lock_item(_clinic_id(), item_id)
    if item is None:
        return _error("Inventory item not found.", 404)

    reactivated = False
    if "is_active" in data:
        if data["is_active"] is not True:
            return _error("Use DELETE to deactivate an item; PATCH can only reactivate it.", 400)
        reactivated = not item.is_active
        item.is_active = True

    _apply_item_fields(item, data, creating=False)
    try:
        db.session.flush()
    except IntegrityError:
        db.session.rollback()
        return _error("An item with this SKU already exists.", 409)

    log_activity(
        action="inventory_item_reactivated" if reactivated else "inventory_item_updated",
        resource_type="inventory_item",
        resource_id=item.id,
        details={"name": item.name, "fields": sorted(data.keys())},
    )
    db.session.commit()
    return jsonify({"data": _serialize_item_fresh(item)})


@inventory_blueprint.delete("/items/<int:item_id>")
@login_required
@require_permission("inventory.delete")
def deactivate_item(item_id):
    """Items are never hard-deleted so their stock history remains intact."""
    item = lock_item(_clinic_id(), item_id)
    if item is None:
        return _error("Inventory item not found.", 404)
    if not item.is_active:
        return jsonify({"data": _serialize_item_fresh(item)})

    item.is_active = False
    log_activity(
        action="inventory_item_deactivated",
        resource_type="inventory_item",
        resource_id=item.id,
        details={"name": item.name, "quantity": format_quantity(item.quantity)},
    )
    db.session.commit()
    return jsonify({"data": _serialize_item_fresh(item)})


# ---------------------------------------------------------------------------
# Movements
# ---------------------------------------------------------------------------

def _movement_query(item_id=None):
    query = db.select(InventoryMovement).where(InventoryMovement.clinic_id == _clinic_id())
    if item_id is not None:
        query = query.where(InventoryMovement.item_id == item_id)
    movement_type = request.args.get("type", "all")
    if movement_type == "write_off":
        query = query.where(InventoryMovement.type.in_(WRITE_OFF_TYPES))
    elif movement_type != "all":
        if movement_type not in MOVEMENT_PERMISSIONS and movement_type != "opening":
            raise InventoryError("Unknown movement type.", 400)
        query = query.where(InventoryMovement.type == movement_type)
    start = parse_optional_date(request.args.get("start_date"), "start_date")
    end = parse_optional_date(request.args.get("end_date"), "end_date")
    if start:
        query = query.where(InventoryMovement.created_at >= datetime.combine(start, datetime.min.time(), timezone.utc))
    if end:
        query = query.where(
            InventoryMovement.created_at < datetime.combine(end + timedelta(days=1), datetime.min.time(), timezone.utc)
        )
    return query


def _paginated_movements(query):
    page, per_page = _pagination()
    total = db.session.scalar(db.select(func.count()).select_from(query.subquery()))
    movements = db.session.scalars(
        query.options(*MOVEMENT_LOAD_OPTIONS)
        .order_by(InventoryMovement.id.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    ).all()
    return jsonify({"data": [_serialize_movement(m) for m in movements], "meta": _meta(page, per_page, total)})


@inventory_blueprint.get("/movements")
@login_required
@require_permission("inventory.read")
def list_movements():
    item_id = _int_arg("item_id")
    return _paginated_movements(_movement_query(item_id))


@inventory_blueprint.get("/items/<int:item_id>/movements")
@login_required
@require_permission("inventory.read")
def list_item_movements(item_id):
    if _scoped(InventoryItem, item_id) is None:
        return _error("Inventory item not found.", 404)
    return _paginated_movements(_movement_query(item_id))


@inventory_blueprint.post("/items/<int:item_id>/movements")
@login_required
@require_permission("inventory.read")
def create_movement(item_id):
    data, error = _json_object()
    if error:
        return error
    if set(data) & SERVER_CONTROLLED_FIELDS:
        return _error("Ownership fields are server-controlled.", 400)
    if set(data) - MOVEMENT_FIELDS:
        return _error("Unsupported stock movement field.", 400)

    movement_type = data.get("type")
    permission = MOVEMENT_PERMISSIONS.get(movement_type)
    if permission is None:
        return _error(
            "type must be one of: " + ", ".join(sorted(MOVEMENT_PERMISSIONS)) + ".",
            422,
        )
    if not user_has_permission(g.current_user, permission):
        return _error("You do not have permission to perform this action.", 403)

    user = g.current_user
    today = _today()
    item = lock_item(user.clinic_id, item_id)
    if item is None:
        return _error("Inventory item not found.", 404)
    if not item.is_active:
        return _error("This item is inactive. Reactivate it before recording stock movements.", 409)

    reference = parse_text(data.get("reference"), "reference", 120)
    reason = parse_text(data.get("reason"), "reason", 255)
    notes = parse_text(data.get("notes"), "notes", 2000)
    reference_type, reference_id = validate_reference(
        user.clinic_id, data.get("reference_type"), data.get("reference_id")
    )
    common = {
        "reference": reference,
        "reason": reason,
        "notes": notes,
        "reference_type": reference_type,
        "reference_id": reference_id,
    }

    if movement_type != "stock_in":
        for field in ("batch_number", "expiry_date", "unit_cost", "supplier_id"):
            if data.get(field) not in (None, ""):
                raise InventoryError(f"{field} only applies when receiving stock.")

    batch = scoped_batch(item, data["batch_id"]) if data.get("batch_id") is not None else None

    if movement_type == "stock_in":
        if batch is not None:
            raise InventoryError("Use batch_number (not batch_id) when receiving stock.")
        supplier_id = _parse_id(data.get("supplier_id"), "supplier_id")
        _assignable_supplier(supplier_id)
        movements = receive_stock(
            item,
            quantity=parse_quantity(data.get("quantity")),
            user=user,
            batch_number=parse_text(data.get("batch_number"), "batch_number", 64),
            expiry_date=parse_optional_date(data.get("expiry_date"), "expiry_date"),
            unit_cost=parse_money(data.get("unit_cost"), "unit_cost"),
            supplier_id=supplier_id,
            **common,
        )
    elif movement_type == "return":
        movements = return_stock(item, quantity=parse_quantity(data.get("quantity")), user=user, batch=batch, **common)
    elif movement_type == "adjustment":
        if not reason:
            raise InventoryError("A reason is required for stock adjustments.")
        new_quantity = data.get("new_quantity")
        delta = data.get("quantity")
        movements = adjust_stock(
            item,
            user=user,
            new_quantity=(
                parse_quantity(new_quantity, "new_quantity", allow_zero=True) if new_quantity is not None else None
            ),
            delta=(
                parse_quantity(delta, "quantity", allow_negative=True) if delta is not None else None
            ),
            batch=batch,
            **common,
        )
    else:
        movements = remove_stock(
            item,
            movement_type=movement_type,
            quantity=parse_quantity(data.get("quantity")),
            user=user,
            today=today,
            batch=batch,
            **common,
        )

    db.session.flush()
    total_change = sum((m.quantity for m in movements), ZERO)
    log_activity(
        action=MOVEMENT_AUDIT_ACTIONS[movement_type],
        resource_type="inventory_item",
        resource_id=item.id,
        details={
            "name": item.name,
            "type": movement_type,
            "quantity": format_quantity(total_change),
            "quantity_after": format_quantity(item.quantity),
            "movement_ids": [m.id for m in movements],
            "reference": reference,
        },
    )
    db.session.commit()

    return jsonify(
        {
            "data": {
                "item": _serialize_item_fresh(item),
                "movements": [_serialize_movement(m) for m in movements],
            }
        }
    ), 201


# ---------------------------------------------------------------------------
# Batches (expiry management)
# ---------------------------------------------------------------------------

@inventory_blueprint.get("/batches")
@login_required
@require_permission("inventory.read")
def list_batches():
    today = _today()
    query = (
        db.select(InventoryBatch, InventoryItem)
        .join(
            InventoryItem,
            and_(InventoryItem.clinic_id == InventoryBatch.clinic_id, InventoryItem.id == InventoryBatch.item_id),
        )
        .where(
            InventoryBatch.clinic_id == _clinic_id(),
            InventoryBatch.quantity > 0,
            InventoryItem.is_active.is_(True),
        )
    )
    status = request.args.get("expiry_status", "attention")
    soon = today + timedelta(days=_warning_days())
    if status == "expired":
        query = query.where(InventoryBatch.expiry_date < today)
    elif status == "expiring_soon":
        query = query.where(InventoryBatch.expiry_date >= today, InventoryBatch.expiry_date <= soon)
    elif status == "attention":
        query = query.where(InventoryBatch.expiry_date <= soon)
    elif status != "all":
        return _error("expiry_status must be one of: all, expired, expiring_soon, attention.", 400)

    item_id = _int_arg("item_id")
    if item_id is not None:
        query = query.where(InventoryBatch.item_id == item_id)

    page, per_page = _pagination()
    total = db.session.scalar(db.select(func.count()).select_from(query.subquery()))
    rows = db.session.execute(
        query.order_by(InventoryBatch.expiry_date.asc().nulls_last(), InventoryBatch.id.asc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    ).all()
    return jsonify(
        {
            "data": [_serialize_batch(batch, item) for batch, item in rows],
            "meta": _meta(page, per_page, total),
        }
    )


# ---------------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------------

def _category_item_counts():
    rows = db.session.execute(
        db.select(InventoryItem.category_id, func.count(InventoryItem.id))
        .where(
            InventoryItem.clinic_id == _clinic_id(),
            InventoryItem.category_id.is_not(None),
            InventoryItem.is_active.is_(True),
        )
        .group_by(InventoryItem.category_id)
    ).all()
    return dict(rows)


def _category_name_taken(name, exclude_id=None):
    query = db.select(InventoryCategory.id).where(
        InventoryCategory.clinic_id == _clinic_id(),
        func.lower(InventoryCategory.name) == name.lower(),
    )
    if exclude_id is not None:
        query = query.where(InventoryCategory.id != exclude_id)
    return db.session.scalar(query) is not None


@inventory_blueprint.get("/categories")
@login_required
@require_permission("inventory.read")
def list_categories():
    query = db.select(InventoryCategory).where(InventoryCategory.clinic_id == _clinic_id())
    active = request.args.get("active", "all")
    if active == "true":
        query = query.where(InventoryCategory.is_active.is_(True))
    elif active == "false":
        query = query.where(InventoryCategory.is_active.is_(False))
    categories = db.session.scalars(query.order_by(InventoryCategory.name.asc())).all()
    counts = _category_item_counts()
    return jsonify({"data": [_serialize_category(c, counts.get(c.id, 0)) for c in categories]})


@inventory_blueprint.post("/categories")
@login_required
@require_permission("inventory.manage_categories")
def create_category():
    data, error = _json_object()
    if error:
        return error
    if set(data) - {"name"}:
        return _error("Unsupported category field.", 400)
    name = parse_text(data.get("name"), "name", 100, required=True)
    if _category_name_taken(name):
        return _error("A category with this name already exists.", 409)

    category = InventoryCategory(clinic_id=_clinic_id(), name=name, is_active=True)
    db.session.add(category)
    try:
        db.session.flush()
    except IntegrityError:
        db.session.rollback()
        return _error("A category with this name already exists.", 409)
    log_activity(
        action="inventory_category_created",
        resource_type="inventory_category",
        resource_id=category.id,
        details={"name": category.name},
    )
    db.session.commit()
    return jsonify({"data": _serialize_category(category, 0)}), 201


@inventory_blueprint.post("/categories/defaults")
@login_required
@require_permission("inventory.manage_categories")
def create_default_categories():
    data = request.get_json(silent=True) or {}
    language = data.get("language", "en") if isinstance(data, dict) else "en"
    names = DEFAULT_CATEGORIES.get(language, DEFAULT_CATEGORIES["en"])

    existing = {
        name.lower()
        for name in db.session.scalars(
            db.select(InventoryCategory.name).where(InventoryCategory.clinic_id == _clinic_id())
        )
    }
    created = []
    for name in names:
        if name.lower() in existing:
            continue
        category = InventoryCategory(clinic_id=_clinic_id(), name=name, is_active=True)
        db.session.add(category)
        created.append(category)
    db.session.flush()
    if created:
        log_activity(
            action="inventory_category_created",
            resource_type="inventory_category",
            details={"defaults": True, "count": len(created), "language": language},
        )
    db.session.commit()
    return jsonify({"data": [_serialize_category(c, 0) for c in created]}), 201


@inventory_blueprint.patch("/categories/<int:category_id>")
@login_required
@require_permission("inventory.manage_categories")
def update_category(category_id):
    data, error = _json_object()
    if error:
        return error
    if set(data) - {"name", "is_active"} or not data:
        return _error("Only name and is_active can be updated.", 400)
    category = _scoped(InventoryCategory, category_id)
    if category is None:
        return _error("Category not found.", 404)

    if "name" in data:
        name = parse_text(data["name"], "name", 100, required=True)
        if _category_name_taken(name, exclude_id=category.id):
            return _error("A category with this name already exists.", 409)
        category.name = name
    if "is_active" in data:
        category.is_active = _parse_bool(data["is_active"], "is_active")

    try:
        db.session.flush()
    except IntegrityError:
        db.session.rollback()
        return _error("A category with this name already exists.", 409)
    log_activity(
        action="inventory_category_updated",
        resource_type="inventory_category",
        resource_id=category.id,
        details={"name": category.name, "is_active": category.is_active},
    )
    db.session.commit()
    return jsonify({"data": _serialize_category(category, _category_item_counts().get(category.id, 0))})


@inventory_blueprint.delete("/categories/<int:category_id>")
@login_required
@require_permission("inventory.manage_categories")
def delete_category(category_id):
    category = _scoped(InventoryCategory, category_id)
    if category is None:
        return _error("Category not found.", 404)
    in_use = db.session.scalar(
        db.select(func.count(InventoryItem.id)).where(
            InventoryItem.clinic_id == category.clinic_id,
            InventoryItem.category_id == category.id,
        )
    )
    if in_use:
        return _error("This category is used by inventory items. Deactivate it instead.", 409)

    log_activity(
        action="inventory_category_deleted",
        resource_type="inventory_category",
        resource_id=category.id,
        details={"name": category.name},
    )
    db.session.delete(category)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return _error("This category is used by inventory items. Deactivate it instead.", 409)
    return "", 204


# ---------------------------------------------------------------------------
# Suppliers
# ---------------------------------------------------------------------------

def _apply_supplier_fields(supplier, data, *, creating):
    if "name" in data or creating:
        supplier.name = parse_text(data.get("name"), "name", 150, required=True)
    for field, limit in (("contact_person", 150), ("phone", 50), ("email", 255), ("address", 1000), ("notes", 2000)):
        if field in data:
            setattr(supplier, field, parse_text(data[field], field, limit))
    if supplier.email and ("@" not in supplier.email or " " in supplier.email):
        raise InventoryError("email must be a valid email address.")
    if "is_active" in data:
        supplier.is_active = _parse_bool(data["is_active"], "is_active")


@inventory_blueprint.get("/suppliers")
@login_required
@require_permission("inventory.read")
def list_suppliers():
    query = db.select(InventorySupplier).where(InventorySupplier.clinic_id == _clinic_id())
    active = request.args.get("active", "all")
    if active == "true":
        query = query.where(InventorySupplier.is_active.is_(True))
    elif active == "false":
        query = query.where(InventorySupplier.is_active.is_(False))
    search = request.args.get("q", "").strip()
    if search:
        pattern = f"%{search}%"
        query = query.where(
            or_(
                InventorySupplier.name.ilike(pattern),
                InventorySupplier.contact_person.ilike(pattern),
                InventorySupplier.phone.ilike(pattern),
                InventorySupplier.email.ilike(pattern),
            )
        )
    suppliers = db.session.scalars(query.order_by(InventorySupplier.name.asc()).limit(500)).all()
    counts = dict(
        db.session.execute(
            db.select(InventoryItem.supplier_id, func.count(InventoryItem.id))
            .where(
                InventoryItem.clinic_id == _clinic_id(),
                InventoryItem.supplier_id.is_not(None),
                InventoryItem.is_active.is_(True),
            )
            .group_by(InventoryItem.supplier_id)
        ).all()
    )
    return jsonify({"data": [_serialize_supplier(s, counts.get(s.id, 0)) for s in suppliers]})


@inventory_blueprint.post("/suppliers")
@login_required
@require_permission("inventory.manage_suppliers")
def create_supplier():
    data, error = _json_object()
    if error:
        return error
    if set(data) & SERVER_CONTROLLED_FIELDS:
        return _error("Ownership fields are server-controlled.", 400)
    if set(data) - SUPPLIER_FIELDS:
        return _error("Unsupported supplier field.", 400)

    supplier = InventorySupplier(clinic_id=_clinic_id(), is_active=True)
    _apply_supplier_fields(supplier, data, creating=True)
    db.session.add(supplier)
    db.session.flush()
    log_activity(
        action="inventory_supplier_created",
        resource_type="inventory_supplier",
        resource_id=supplier.id,
        details={"name": supplier.name},
    )
    db.session.commit()
    return jsonify({"data": _serialize_supplier(supplier, 0)}), 201


@inventory_blueprint.patch("/suppliers/<int:supplier_id>")
@login_required
@require_permission("inventory.manage_suppliers")
def update_supplier(supplier_id):
    data, error = _json_object()
    if error:
        return error
    if set(data) & SERVER_CONTROLLED_FIELDS:
        return _error("Ownership fields are server-controlled.", 400)
    if set(data) - SUPPLIER_FIELDS or not data:
        return _error("Unsupported supplier field.", 400)
    supplier = _scoped(InventorySupplier, supplier_id)
    if supplier is None:
        return _error("Supplier not found.", 404)

    _apply_supplier_fields(supplier, data, creating=False)
    log_activity(
        action="inventory_supplier_updated",
        resource_type="inventory_supplier",
        resource_id=supplier.id,
        details={"name": supplier.name, "fields": sorted(data.keys()), "is_active": supplier.is_active},
    )
    db.session.commit()
    return jsonify({"data": _serialize_supplier(supplier)})


@inventory_blueprint.delete("/suppliers/<int:supplier_id>")
@login_required
@require_permission("inventory.manage_suppliers")
def delete_supplier(supplier_id):
    supplier = _scoped(InventorySupplier, supplier_id)
    if supplier is None:
        return _error("Supplier not found.", 404)

    referenced = any(
        db.session.scalar(
            db.select(model.id).where(model.clinic_id == supplier.clinic_id, model.supplier_id == supplier.id).limit(1)
        )
        is not None
        for model in (InventoryItem, InventoryBatch, InventoryMovement)
    )
    if referenced:
        return _error("This supplier is referenced by inventory records. Deactivate it instead.", 409)

    log_activity(
        action="inventory_supplier_deleted",
        resource_type="inventory_supplier",
        resource_id=supplier.id,
        details={"name": supplier.name},
    )
    db.session.delete(supplier)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return _error("This supplier is referenced by inventory records. Deactivate it instead.", 409)
    return "", 204
