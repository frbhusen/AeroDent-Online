"""add_inventory

Revision ID: b1c2d3e4f5a6
Revises: 10d4e5f6a7b8
Create Date: 2026-09-26 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b1c2d3e4f5a6'
down_revision = '10d4e5f6a7b8'
branch_labels = None
depends_on = None


MOVEMENT_TYPES = (
    "adjustment", "damaged", "expired", "loss", "opening",
    "return", "stock_in", "supplier_return", "usage",
)


def _timestamps():
    return [
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def _clinic_fk_column():
    return sa.Column('clinic_id', sa.Integer(), sa.ForeignKey('clinics.id', ondelete='CASCADE'), nullable=False)


def upgrade():
    op.add_column(
        'clinics',
        sa.Column('inventory_expiry_warning_days', sa.Integer(), server_default='60', nullable=False),
    )

    # 1. Categories
    op.create_table(
        'inventory_categories',
        sa.Column('id', sa.Integer(), primary_key=True),
        _clinic_fk_column(),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default=sa.true(), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint('clinic_id', 'id', name='uq_inventory_category_clinic_id'),
    )
    op.create_index('ix_inventory_categories_clinic_id', 'inventory_categories', ['clinic_id'])
    op.create_index(
        'uq_inventory_category_clinic_name',
        'inventory_categories',
        ['clinic_id', sa.text('lower(name)')],
        unique=True,
    )

    # 2. Suppliers
    op.create_table(
        'inventory_suppliers',
        sa.Column('id', sa.Integer(), primary_key=True),
        _clinic_fk_column(),
        sa.Column('name', sa.String(length=150), nullable=False),
        sa.Column('contact_person', sa.String(length=150), nullable=True),
        sa.Column('phone', sa.String(length=50), nullable=True),
        sa.Column('email', sa.String(length=255), nullable=True),
        sa.Column('address', sa.Text(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default=sa.true(), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint('clinic_id', 'id', name='uq_inventory_supplier_clinic_id'),
    )
    op.create_index('ix_inventory_suppliers_clinic_id', 'inventory_suppliers', ['clinic_id'])

    # 3. Items
    op.create_table(
        'inventory_items',
        sa.Column('id', sa.Integer(), primary_key=True),
        _clinic_fk_column(),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('sku', sa.String(length=64), nullable=True),
        sa.Column('barcode', sa.String(length=64), nullable=True),
        sa.Column('category_id', sa.Integer(), nullable=True),
        sa.Column('supplier_id', sa.Integer(), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('unit', sa.String(length=30), server_default='piece', nullable=False),
        sa.Column('quantity', sa.Numeric(12, 3), server_default='0', nullable=False),
        sa.Column('minimum_quantity', sa.Numeric(12, 3), server_default='0', nullable=False),
        sa.Column('cost_per_unit', sa.Numeric(12, 2), nullable=True),
        sa.Column('location', sa.String(length=120), nullable=True),
        sa.Column('track_batches', sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column('created_by', sa.Integer(), nullable=True),
        *_timestamps(),
        sa.UniqueConstraint('clinic_id', 'id', name='uq_inventory_item_clinic_id'),
        sa.CheckConstraint('quantity >= 0', name='ck_inventory_item_quantity_non_negative'),
        sa.CheckConstraint('minimum_quantity >= 0', name='ck_inventory_item_minimum_non_negative'),
        sa.CheckConstraint('cost_per_unit IS NULL OR cost_per_unit >= 0', name='ck_inventory_item_cost_non_negative'),
        sa.ForeignKeyConstraint(
            ['clinic_id', 'category_id'],
            ['inventory_categories.clinic_id', 'inventory_categories.id'],
            name='fk_inventory_item_category_clinic',
        ),
        sa.ForeignKeyConstraint(
            ['clinic_id', 'supplier_id'],
            ['inventory_suppliers.clinic_id', 'inventory_suppliers.id'],
            name='fk_inventory_item_supplier_clinic',
        ),
        sa.ForeignKeyConstraint(
            ['clinic_id', 'created_by'],
            ['users.clinic_id', 'users.id'],
            name='fk_inventory_item_created_by_clinic',
        ),
    )
    op.create_index('ix_inventory_items_clinic_id', 'inventory_items', ['clinic_id'])
    op.create_index('ix_inventory_items_barcode', 'inventory_items', ['barcode'])
    op.create_index('ix_inventory_items_category_id', 'inventory_items', ['category_id'])
    op.create_index('ix_inventory_items_supplier_id', 'inventory_items', ['supplier_id'])
    op.create_index('ix_inventory_items_is_active', 'inventory_items', ['is_active'])
    op.create_index(
        'uq_inventory_item_clinic_sku',
        'inventory_items',
        ['clinic_id', sa.text('lower(sku)')],
        unique=True,
        postgresql_where=sa.text('sku IS NOT NULL'),
    )

    # 4. Batches / lots
    op.create_table(
        'inventory_batches',
        sa.Column('id', sa.Integer(), primary_key=True),
        _clinic_fk_column(),
        sa.Column('item_id', sa.Integer(), nullable=False),
        sa.Column('batch_number', sa.String(length=64), nullable=True),
        sa.Column('quantity', sa.Numeric(12, 3), server_default='0', nullable=False),
        sa.Column('unit_cost', sa.Numeric(12, 2), nullable=True),
        sa.Column('expiry_date', sa.Date(), nullable=True),
        sa.Column('supplier_id', sa.Integer(), nullable=True),
        sa.Column('received_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint('clinic_id', 'id', name='uq_inventory_batch_clinic_id'),
        sa.CheckConstraint('quantity >= 0', name='ck_inventory_batch_quantity_non_negative'),
        sa.CheckConstraint('unit_cost IS NULL OR unit_cost >= 0', name='ck_inventory_batch_cost_non_negative'),
        sa.ForeignKeyConstraint(
            ['clinic_id', 'item_id'],
            ['inventory_items.clinic_id', 'inventory_items.id'],
            name='fk_inventory_batch_item_clinic',
        ),
        sa.ForeignKeyConstraint(
            ['clinic_id', 'supplier_id'],
            ['inventory_suppliers.clinic_id', 'inventory_suppliers.id'],
            name='fk_inventory_batch_supplier_clinic',
        ),
    )
    op.create_index('ix_inventory_batches_clinic_id', 'inventory_batches', ['clinic_id'])
    op.create_index('ix_inventory_batches_item_id', 'inventory_batches', ['item_id'])
    op.create_index('ix_inventory_batches_expiry_date', 'inventory_batches', ['expiry_date'])
    op.create_index('ix_inventory_batches_item_expiry', 'inventory_batches', ['item_id', 'expiry_date'])

    # 5. Movements (append-only ledger)
    op.create_table(
        'inventory_movements',
        sa.Column('id', sa.Integer(), primary_key=True),
        _clinic_fk_column(),
        sa.Column('item_id', sa.Integer(), nullable=False),
        sa.Column('batch_id', sa.Integer(), nullable=True),
        sa.Column('type', sa.String(length=30), nullable=False),
        sa.Column('quantity', sa.Numeric(12, 3), nullable=False),
        sa.Column('quantity_after', sa.Numeric(12, 3), nullable=False),
        sa.Column('unit_cost', sa.Numeric(12, 2), nullable=True),
        sa.Column('supplier_id', sa.Integer(), nullable=True),
        sa.Column('reference', sa.String(length=120), nullable=True),
        sa.Column('reason', sa.String(length=255), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('reference_type', sa.String(length=30), nullable=True),
        sa.Column('reference_id', sa.Integer(), nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "type IN (" + ", ".join(f"'{name}'" for name in MOVEMENT_TYPES) + ")",
            name='ck_inventory_movement_type',
        ),
        sa.CheckConstraint('quantity <> 0', name='ck_inventory_movement_quantity_non_zero'),
        sa.CheckConstraint('quantity_after >= 0', name='ck_inventory_movement_balance_non_negative'),
        sa.CheckConstraint(
            "reference_type IS NULL OR reference_type IN ('patient', 'treatment', 'appointment')",
            name='ck_inventory_movement_reference_type',
        ),
        sa.ForeignKeyConstraint(
            ['clinic_id', 'item_id'],
            ['inventory_items.clinic_id', 'inventory_items.id'],
            name='fk_inventory_movement_item_clinic',
        ),
        sa.ForeignKeyConstraint(
            ['clinic_id', 'batch_id'],
            ['inventory_batches.clinic_id', 'inventory_batches.id'],
            name='fk_inventory_movement_batch_clinic',
        ),
        sa.ForeignKeyConstraint(
            ['clinic_id', 'supplier_id'],
            ['inventory_suppliers.clinic_id', 'inventory_suppliers.id'],
            name='fk_inventory_movement_supplier_clinic',
        ),
        sa.ForeignKeyConstraint(
            ['clinic_id', 'created_by'],
            ['users.clinic_id', 'users.id'],
            name='fk_inventory_movement_created_by_clinic',
        ),
    )
    op.create_index('ix_inventory_movements_clinic_id', 'inventory_movements', ['clinic_id'])
    op.create_index('ix_inventory_movements_item_id', 'inventory_movements', ['item_id'])
    op.create_index('ix_inventory_movements_batch_id', 'inventory_movements', ['batch_id'])
    op.create_index('ix_inventory_movements_type', 'inventory_movements', ['type'])
    op.create_index('ix_inventory_movements_created_at', 'inventory_movements', ['created_at'])
    op.create_index('ix_inventory_movements_item_created', 'inventory_movements', ['item_id', 'created_at'])


def downgrade():
    op.drop_table('inventory_movements')
    op.drop_table('inventory_batches')
    op.drop_table('inventory_items')
    op.drop_table('inventory_suppliers')
    op.drop_table('inventory_categories')
    op.drop_column('clinics', 'inventory_expiry_warning_days')
