from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, ForeignKeyConstraint, Index, UniqueConstraint, event, text

from backend.extensions import db


# Movement types and the direction each one moves stock. "adjustment" is signed by the caller
# (a physical count correction can go either way); every other type has a fixed direction.
MOVEMENT_DIRECTIONS = {
    "opening": 1,
    "stock_in": 1,
    "return": 1,
    "usage": -1,
    "supplier_return": -1,
    "expired": -1,
    "damaged": -1,
    "loss": -1,
    "adjustment": 0,
}
MOVEMENT_TYPES = frozenset(MOVEMENT_DIRECTIONS)

_MOVEMENT_TYPE_SQL = ", ".join(f"'{name}'" for name in sorted(MOVEMENT_TYPES))


def _utcnow():
    return datetime.now(timezone.utc)


class InventoryCategory(db.Model):
    __tablename__ = "inventory_categories"

    __table_args__ = (
        UniqueConstraint("clinic_id", "id", name="uq_inventory_category_clinic_id"),
        Index(
            "uq_inventory_category_clinic_name",
            "clinic_id",
            text("lower(name)"),
            unique=True,
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    clinic_id = db.Column(db.Integer, db.ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class InventorySupplier(db.Model):
    __tablename__ = "inventory_suppliers"

    __table_args__ = (
        UniqueConstraint("clinic_id", "id", name="uq_inventory_supplier_clinic_id"),
    )

    id = db.Column(db.Integer, primary_key=True)
    clinic_id = db.Column(db.Integer, db.ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False, index=True)
    name = db.Column(db.String(150), nullable=False)
    contact_person = db.Column(db.String(150), nullable=True)
    phone = db.Column(db.String(50), nullable=True)
    email = db.Column(db.String(255), nullable=True)
    address = db.Column(db.Text, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class InventoryItem(db.Model):
    __tablename__ = "inventory_items"

    __table_args__ = (
        UniqueConstraint("clinic_id", "id", name="uq_inventory_item_clinic_id"),
        CheckConstraint("quantity >= 0", name="ck_inventory_item_quantity_non_negative"),
        CheckConstraint("minimum_quantity >= 0", name="ck_inventory_item_minimum_non_negative"),
        CheckConstraint(
            "cost_per_unit IS NULL OR cost_per_unit >= 0",
            name="ck_inventory_item_cost_non_negative",
        ),
        ForeignKeyConstraint(
            ["clinic_id", "category_id"],
            ["inventory_categories.clinic_id", "inventory_categories.id"],
            name="fk_inventory_item_category_clinic",
        ),
        ForeignKeyConstraint(
            ["clinic_id", "supplier_id"],
            ["inventory_suppliers.clinic_id", "inventory_suppliers.id"],
            name="fk_inventory_item_supplier_clinic",
        ),
        ForeignKeyConstraint(
            ["clinic_id", "created_by"],
            ["users.clinic_id", "users.id"],
            name="fk_inventory_item_created_by_clinic",
        ),
        # SKUs are optional but, when present, must be unique inside one clinic.
        Index(
            "uq_inventory_item_clinic_sku",
            "clinic_id",
            text("lower(sku)"),
            unique=True,
            postgresql_where=text("sku IS NOT NULL"),
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    clinic_id = db.Column(db.Integer, db.ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False, index=True)
    name = db.Column(db.String(200), nullable=False)
    sku = db.Column(db.String(64), nullable=True)
    barcode = db.Column(db.String(64), nullable=True, index=True)
    category_id = db.Column(db.Integer, nullable=True, index=True)
    supplier_id = db.Column(db.Integer, nullable=True, index=True)
    description = db.Column(db.Text, nullable=True)
    unit = db.Column(db.String(30), nullable=False, default="piece")
    # Server-maintained running balance. Only changed through InventoryMovement records.
    quantity = db.Column(db.Numeric(12, 3), nullable=False, default=0)
    minimum_quantity = db.Column(db.Numeric(12, 3), nullable=False, default=0)
    # Most recent known unit cost (updated when stock is received with a cost).
    cost_per_unit = db.Column(db.Numeric(12, 2), nullable=True)
    location = db.Column(db.String(120), nullable=True)
    # When true, stock is held in InventoryBatch rows (lot number / expiry date) and
    # quantity always equals the sum of the item's batch quantities.
    track_batches = db.Column(db.Boolean, nullable=False, default=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True, index=True)
    created_by = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    category = db.relationship(
        "InventoryCategory",
        primaryjoin="and_(InventoryCategory.clinic_id == InventoryItem.clinic_id, "
        "InventoryCategory.id == InventoryItem.category_id)",
        foreign_keys="InventoryItem.category_id",
        viewonly=True,
    )
    supplier = db.relationship(
        "InventorySupplier",
        primaryjoin="and_(InventorySupplier.clinic_id == InventoryItem.clinic_id, "
        "InventorySupplier.id == InventoryItem.supplier_id)",
        foreign_keys="InventoryItem.supplier_id",
        viewonly=True,
    )


class InventoryBatch(db.Model):
    __tablename__ = "inventory_batches"

    __table_args__ = (
        UniqueConstraint("clinic_id", "id", name="uq_inventory_batch_clinic_id"),
        CheckConstraint("quantity >= 0", name="ck_inventory_batch_quantity_non_negative"),
        CheckConstraint(
            "unit_cost IS NULL OR unit_cost >= 0",
            name="ck_inventory_batch_cost_non_negative",
        ),
        ForeignKeyConstraint(
            ["clinic_id", "item_id"],
            ["inventory_items.clinic_id", "inventory_items.id"],
            name="fk_inventory_batch_item_clinic",
        ),
        ForeignKeyConstraint(
            ["clinic_id", "supplier_id"],
            ["inventory_suppliers.clinic_id", "inventory_suppliers.id"],
            name="fk_inventory_batch_supplier_clinic",
        ),
        Index("ix_inventory_batches_item_expiry", "item_id", "expiry_date"),
    )

    id = db.Column(db.Integer, primary_key=True)
    clinic_id = db.Column(db.Integer, db.ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False, index=True)
    item_id = db.Column(db.Integer, nullable=False, index=True)
    batch_number = db.Column(db.String(64), nullable=True)
    quantity = db.Column(db.Numeric(12, 3), nullable=False, default=0)
    unit_cost = db.Column(db.Numeric(12, 2), nullable=True)
    expiry_date = db.Column(db.Date, nullable=True, index=True)
    supplier_id = db.Column(db.Integer, nullable=True)
    received_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utcnow)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    supplier = db.relationship(
        "InventorySupplier",
        primaryjoin="and_(InventorySupplier.clinic_id == InventoryBatch.clinic_id, "
        "InventorySupplier.id == InventoryBatch.supplier_id)",
        foreign_keys="InventoryBatch.supplier_id",
        viewonly=True,
    )


class InventoryMovement(db.Model):
    """Append-only stock ledger. Rows are never updated; mistakes are corrected with new movements."""

    __tablename__ = "inventory_movements"

    __table_args__ = (
        CheckConstraint(f"type IN ({_MOVEMENT_TYPE_SQL})", name="ck_inventory_movement_type"),
        CheckConstraint("quantity <> 0", name="ck_inventory_movement_quantity_non_zero"),
        CheckConstraint("quantity_after >= 0", name="ck_inventory_movement_balance_non_negative"),
        CheckConstraint(
            "reference_type IS NULL OR reference_type IN ('patient', 'treatment', 'appointment')",
            name="ck_inventory_movement_reference_type",
        ),
        ForeignKeyConstraint(
            ["clinic_id", "item_id"],
            ["inventory_items.clinic_id", "inventory_items.id"],
            name="fk_inventory_movement_item_clinic",
        ),
        ForeignKeyConstraint(
            ["clinic_id", "batch_id"],
            ["inventory_batches.clinic_id", "inventory_batches.id"],
            name="fk_inventory_movement_batch_clinic",
        ),
        ForeignKeyConstraint(
            ["clinic_id", "supplier_id"],
            ["inventory_suppliers.clinic_id", "inventory_suppliers.id"],
            name="fk_inventory_movement_supplier_clinic",
        ),
        ForeignKeyConstraint(
            ["clinic_id", "created_by"],
            ["users.clinic_id", "users.id"],
            name="fk_inventory_movement_created_by_clinic",
        ),
        Index("ix_inventory_movements_item_created", "item_id", "created_at"),
    )

    id = db.Column(db.Integer, primary_key=True)
    clinic_id = db.Column(db.Integer, db.ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False, index=True)
    item_id = db.Column(db.Integer, nullable=False, index=True)
    batch_id = db.Column(db.Integer, nullable=True, index=True)
    type = db.Column(db.String(30), nullable=False, index=True)
    # Signed change applied to the item's stock (positive = in, negative = out).
    quantity = db.Column(db.Numeric(12, 3), nullable=False)
    # Item balance immediately after this movement, so history reads like a ledger.
    quantity_after = db.Column(db.Numeric(12, 3), nullable=False)
    unit_cost = db.Column(db.Numeric(12, 2), nullable=True)
    supplier_id = db.Column(db.Integer, nullable=True)
    reference = db.Column(db.String(120), nullable=True)
    reason = db.Column(db.String(255), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    # Optional loose link to a clinical record (validated as same-clinic when written;
    # intentionally not a foreign key so clinical records stay independently deletable).
    reference_type = db.Column(db.String(30), nullable=True)
    reference_id = db.Column(db.Integer, nullable=True)
    created_by = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utcnow, index=True)

    item = db.relationship(
        "InventoryItem",
        primaryjoin="and_(InventoryItem.clinic_id == InventoryMovement.clinic_id, "
        "InventoryItem.id == InventoryMovement.item_id)",
        foreign_keys="InventoryMovement.item_id",
        viewonly=True,
    )
    batch = db.relationship(
        "InventoryBatch",
        primaryjoin="and_(InventoryBatch.clinic_id == InventoryMovement.clinic_id, "
        "InventoryBatch.id == InventoryMovement.batch_id)",
        foreign_keys="InventoryMovement.batch_id",
        viewonly=True,
    )
    supplier = db.relationship(
        "InventorySupplier",
        primaryjoin="and_(InventorySupplier.clinic_id == InventoryMovement.clinic_id, "
        "InventorySupplier.id == InventoryMovement.supplier_id)",
        foreign_keys="InventoryMovement.supplier_id",
        viewonly=True,
    )
    creator = db.relationship(
        "User",
        primaryjoin="and_(User.clinic_id == InventoryMovement.clinic_id, User.id == InventoryMovement.created_by)",
        foreign_keys="InventoryMovement.created_by",
        viewonly=True,
    )


@event.listens_for(InventoryMovement, "before_update")
def _reject_movement_update(mapper, connection, target):
    raise ValueError("Inventory movements are append-only and cannot be modified.")
