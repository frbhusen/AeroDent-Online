"""
Server-authoritative inventory stock operations.

Every function here mutates stock only through InventoryMovement rows and expects to run
inside the caller's transaction: the caller locks the item with ``lock_item`` first, calls
one operation, then commits (or rolls back on InventoryError). Nothing here commits.

Invariants maintained:
  * item.quantity >= 0 and batch.quantity >= 0 (also enforced by DB check constraints)
  * for batch-tracked items, item.quantity == sum(batch.quantity)
  * every change to item.quantity has exactly one movement per touched batch (or one
    movement for untracked items) whose ``quantity_after`` is the item balance after it
"""

from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from sqlalchemy import and_, case, exists, func, or_

from backend.extensions import db
from backend.models import (
    Appointment,
    InventoryBatch,
    InventoryItem,
    InventoryMovement,
    Patient,
    Treatment,
)


QUANTITY_PLACES = Decimal("0.001")
MONEY_PLACES = Decimal("0.01")
MAX_QUANTITY = Decimal("999999999.999")
MAX_MONEY = Decimal("9999999999.99")
ZERO = Decimal("0")

REFERENCE_MODELS = {
    "patient": Patient,
    "treatment": Treatment,
    "appointment": Appointment,
}


class InventoryError(Exception):
    def __init__(self, message, status=422):
        super().__init__(message)
        self.message = message
        self.status = status


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def _to_decimal(value, field):
    if isinstance(value, bool) or value is None:
        raise InventoryError(f"{field} must be a number.")
    if isinstance(value, (int, Decimal)):
        number = Decimal(value)
    elif isinstance(value, float):
        number = Decimal(str(value))
    elif isinstance(value, str) and value.strip():
        try:
            number = Decimal(value.strip())
        except InvalidOperation:
            raise InventoryError(f"{field} must be a number.")
    else:
        raise InventoryError(f"{field} must be a number.")
    if not number.is_finite():
        raise InventoryError(f"{field} must be a finite number.")
    return number


def parse_quantity(value, field="quantity", *, allow_zero=False, allow_negative=False):
    number = _to_decimal(value, field)
    if number != number.quantize(QUANTITY_PLACES):
        raise InventoryError(f"{field} supports at most 3 decimal places.")
    if not allow_negative and number < 0:
        raise InventoryError(f"{field} must not be negative.")
    if not allow_zero and number == 0:
        raise InventoryError(f"{field} must not be zero." if allow_negative else f"{field} must be greater than zero.")
    if abs(number) > MAX_QUANTITY:
        raise InventoryError(f"{field} is too large.")
    return number.quantize(QUANTITY_PLACES)


def parse_money(value, field):
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    number = _to_decimal(value, field)
    if number < 0:
        raise InventoryError(f"{field} must not be negative.")
    if number != number.quantize(MONEY_PLACES):
        raise InventoryError(f"{field} supports at most 2 decimal places.")
    if number > MAX_MONEY:
        raise InventoryError(f"{field} is too large.")
    return number.quantize(MONEY_PLACES)


def parse_optional_date(value, field):
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if not isinstance(value, str):
        raise InventoryError(f"{field} must be an ISO date (YYYY-MM-DD).")
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        raise InventoryError(f"{field} must be an ISO date (YYYY-MM-DD).")


def parse_text(value, field, max_length, *, required=False):
    if value is None:
        if required:
            raise InventoryError(f"{field} is required.")
        return None
    if not isinstance(value, str):
        raise InventoryError(f"{field} must be a string.")
    stripped = value.strip()
    if required and not stripped:
        raise InventoryError(f"{field} is required.")
    if max_length and len(stripped) > max_length:
        raise InventoryError(f"{field} is too long (maximum {max_length} characters).")
    return stripped or None


def format_quantity(value):
    if value is None:
        return None
    normalized = Decimal(value).normalize()
    if normalized == 0:
        return "0"
    return format(normalized, "f")


def format_money(value):
    if value is None:
        return None
    return format(Decimal(value).quantize(MONEY_PLACES), "f")


# ---------------------------------------------------------------------------
# Expiry / status
# ---------------------------------------------------------------------------

def expiry_window_days(clinic):
    days = getattr(clinic, "inventory_expiry_warning_days", None)
    return days if isinstance(days, int) and days > 0 else 60


def expiry_status_for(expiry_date, today, warning_days):
    if expiry_date is None:
        return "none"
    if expiry_date < today:
        return "expired"
    if expiry_date <= today + timedelta(days=warning_days):
        return "expiring_soon"
    return "ok"


def stock_status_for(usable_quantity, minimum_quantity):
    if usable_quantity <= 0:
        return "out"
    if usable_quantity <= minimum_quantity:
        return "low"
    return "ok"


def item_status_columns(today, warning_days):
    """
    Correlated SQL expressions computing each item's stock/expiry state, usable by both list
    queries (for filtering/sorting) and dashboard aggregates. Expired batch stock is excluded
    from usable quantity: it is still physically on hand until written off, but not usable.
    """
    batch_matches_item = and_(
        InventoryBatch.clinic_id == InventoryItem.clinic_id,
        InventoryBatch.item_id == InventoryItem.id,
        InventoryBatch.quantity > 0,
    )
    expired_quantity = (
        db.select(func.coalesce(func.sum(InventoryBatch.quantity), ZERO))
        .where(batch_matches_item, InventoryBatch.expiry_date < today)
        .correlate(InventoryItem)
        .scalar_subquery()
    )
    nearest_expiry = (
        db.select(func.min(InventoryBatch.expiry_date))
        .where(batch_matches_item, InventoryBatch.expiry_date.is_not(None))
        .correlate(InventoryItem)
        .scalar_subquery()
    )
    has_expired = exists().where(batch_matches_item, InventoryBatch.expiry_date < today).correlate(InventoryItem)
    has_expiring = (
        exists()
        .where(
            batch_matches_item,
            InventoryBatch.expiry_date >= today,
            InventoryBatch.expiry_date <= today + timedelta(days=warning_days),
        )
        .correlate(InventoryItem)
    )
    usable_quantity = InventoryItem.quantity - expired_quantity
    stock_status = case(
        (usable_quantity <= 0, "out"),
        (usable_quantity <= InventoryItem.minimum_quantity, "low"),
        else_="ok",
    )
    return {
        "expired_quantity": expired_quantity,
        "usable_quantity": usable_quantity,
        "nearest_expiry": nearest_expiry,
        "has_expired": has_expired,
        "has_expiring": has_expiring,
        "stock_status": stock_status,
    }


# ---------------------------------------------------------------------------
# Locking / lookups
# ---------------------------------------------------------------------------

def lock_item(clinic_id, item_id):
    """Loads a clinic-scoped item with a row lock so concurrent stock writes serialize."""
    return db.session.scalar(
        db.select(InventoryItem)
        .where(InventoryItem.id == item_id, InventoryItem.clinic_id == clinic_id)
        .with_for_update()
    )


def _locked_batches(item, *, pool=None, today=None):
    query = db.select(InventoryBatch).where(
        InventoryBatch.clinic_id == item.clinic_id,
        InventoryBatch.item_id == item.id,
        InventoryBatch.quantity > 0,
    )
    if pool == "usable":
        query = query.where(or_(InventoryBatch.expiry_date.is_(None), InventoryBatch.expiry_date >= today))
    elif pool == "expired":
        query = query.where(InventoryBatch.expiry_date < today)
    # First-expiry-first-out; batches without an expiry date are used last.
    query = query.order_by(
        InventoryBatch.expiry_date.is_(None),
        InventoryBatch.expiry_date.asc(),
        InventoryBatch.id.asc(),
    )
    return db.session.scalars(query.with_for_update()).all()


def scoped_batch(item, batch_id):
    if isinstance(batch_id, bool) or not isinstance(batch_id, int):
        raise InventoryError("batch_id must be an integer.")
    batch = db.session.scalar(
        db.select(InventoryBatch)
        .where(
            InventoryBatch.id == batch_id,
            InventoryBatch.clinic_id == item.clinic_id,
            InventoryBatch.item_id == item.id,
        )
        .with_for_update()
    )
    if batch is None:
        raise InventoryError("Batch not found for this item.", 404)
    return batch


def validate_reference(clinic_id, reference_type, reference_id):
    if reference_type is None and reference_id is None:
        return None, None
    if reference_type not in REFERENCE_MODELS:
        raise InventoryError("reference_type must be one of: patient, treatment, appointment.")
    if isinstance(reference_id, bool) or not isinstance(reference_id, int):
        raise InventoryError("reference_id must be an integer.")
    model = REFERENCE_MODELS[reference_type]
    found = db.session.scalar(
        db.select(model.id).where(model.id == reference_id, model.clinic_id == clinic_id)
    )
    if found is None:
        raise InventoryError(f"Referenced {reference_type} not found.", 404)
    return reference_type, reference_id


# ---------------------------------------------------------------------------
# Stock operations
# ---------------------------------------------------------------------------

def _movement(item, *, movement_type, delta, user, batch=None, **fields):
    movement = InventoryMovement(
        clinic_id=item.clinic_id,
        item_id=item.id,
        batch_id=batch.id if batch is not None else None,
        type=movement_type,
        quantity=delta,
        quantity_after=item.quantity,
        created_by=user.id,
        **fields,
    )
    db.session.add(movement)
    return movement


def receive_stock(
    item,
    *,
    quantity,
    user,
    movement_type="stock_in",
    batch_number=None,
    expiry_date=None,
    unit_cost=None,
    supplier_id=None,
    **fields,
):
    batch = None
    if item.track_batches:
        if batch_number:
            batch = db.session.scalar(
                db.select(InventoryBatch)
                .where(
                    InventoryBatch.clinic_id == item.clinic_id,
                    InventoryBatch.item_id == item.id,
                    func.lower(InventoryBatch.batch_number) == batch_number.lower(),
                )
                .with_for_update()
            )
            if batch is not None and expiry_date is not None and batch.expiry_date != expiry_date:
                raise InventoryError(
                    "This batch number already exists with a different expiry date.", 409
                )
        if batch is None:
            batch = InventoryBatch(
                clinic_id=item.clinic_id,
                item_id=item.id,
                batch_number=batch_number,
                quantity=ZERO,
                unit_cost=unit_cost,
                expiry_date=expiry_date,
                supplier_id=supplier_id,
            )
            db.session.add(batch)
            db.session.flush()
        elif unit_cost is not None:
            batch.unit_cost = unit_cost
        batch.quantity = batch.quantity + quantity
    elif batch_number or expiry_date:
        raise InventoryError(
            "Enable batch tracking on this item to record batch numbers or expiry dates."
        )

    item.quantity = item.quantity + quantity
    if unit_cost is not None:
        item.cost_per_unit = unit_cost

    return [
        _movement(
            item,
            movement_type=movement_type,
            delta=quantity,
            user=user,
            batch=batch,
            unit_cost=unit_cost,
            supplier_id=supplier_id,
            **fields,
        )
    ]


def remove_stock(item, *, movement_type, quantity, user, today, batch=None, **fields):
    """Usage and write-offs (expired / damaged / loss / supplier_return). Never goes negative."""
    if not item.track_batches:
        if batch is not None:
            raise InventoryError("This item does not track batches.")
        if quantity > item.quantity:
            raise InventoryError(
                f"Insufficient stock: {format_quantity(item.quantity)} {item.unit} available.", 409
            )
        item.quantity = item.quantity - quantity
        return [_movement(item, movement_type=movement_type, delta=-quantity, user=user, **fields)]

    if batch is not None:
        if movement_type == "usage" and batch.expiry_date is not None and batch.expiry_date < today:
            raise InventoryError(
                "This batch has expired and cannot be used. Record it as an expired write-off instead.",
                409,
            )
        if quantity > batch.quantity:
            raise InventoryError(
                f"Insufficient stock in this batch: {format_quantity(batch.quantity)} {item.unit} available.",
                409,
            )
        batches = [batch]
    else:
        pool = {"usage": "usable", "expired": "expired"}.get(movement_type)
        batches = _locked_batches(item, pool=pool, today=today)
        available = sum((b.quantity for b in batches), ZERO)
        if quantity > available:
            label = {
                "usable": "usable (non-expired)",
                "expired": "expired",
            }.get(pool, "")
            raise InventoryError(
                f"Insufficient {label + ' ' if label else ''}stock: "
                f"{format_quantity(available)} {item.unit} available.",
                409,
            )

    movements = []
    remaining = quantity
    for current in batches:
        if remaining <= 0:
            break
        take = min(remaining, current.quantity)
        if take <= 0:
            continue
        current.quantity = current.quantity - take
        item.quantity = item.quantity - take
        remaining -= take
        movements.append(
            _movement(item, movement_type=movement_type, delta=-take, user=user, batch=current, **fields)
        )
    return movements


def return_stock(item, *, quantity, user, batch=None, **fields):
    """Unused stock coming back into inventory (e.g. an unopened pack returned from a surgery)."""
    if item.track_batches:
        if batch is None:
            raise InventoryError("batch_id is required to return stock for a batch-tracked item.")
        batch.quantity = batch.quantity + quantity
    elif batch is not None:
        raise InventoryError("This item does not track batches.")
    item.quantity = item.quantity + quantity
    return [_movement(item, movement_type="return", delta=quantity, user=user, batch=batch, **fields)]


def adjust_stock(item, *, user, new_quantity=None, delta=None, batch=None, **fields):
    """Physical count correction. Exactly one of new_quantity / delta must be given."""
    if (new_quantity is None) == (delta is None):
        raise InventoryError("Provide either new_quantity or quantity (a signed adjustment).")
    if item.track_batches:
        if batch is None:
            raise InventoryError("batch_id is required to adjust a batch-tracked item.")
        current = batch.quantity
    else:
        if batch is not None:
            raise InventoryError("This item does not track batches.")
        current = item.quantity

    if delta is None:
        delta = new_quantity - current
    if delta == 0:
        raise InventoryError("The adjustment does not change the stock quantity.")
    if current + delta < 0:
        raise InventoryError(
            f"Adjustment would make stock negative ({format_quantity(current)} {item.unit} on hand).",
            409,
        )

    if batch is not None:
        batch.quantity = batch.quantity + delta
    item.quantity = item.quantity + delta
    return [_movement(item, movement_type="adjustment", delta=delta, user=user, batch=batch, **fields)]
