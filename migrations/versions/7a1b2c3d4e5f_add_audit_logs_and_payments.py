"""add_audit_logs_and_payments

Revision ID: 7a1b2c3d4e5f
Revises: 6f2f3385d0ef
Create Date: 2026-09-24 21:51:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '7a1b2c3d4e5f'
down_revision = '6f2f3385d0ef'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'audit_logs',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('clinic_id', sa.Integer(), sa.ForeignKey('clinics.id', ondelete='CASCADE'), nullable=True),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('user_name', sa.String(length=120), nullable=True),
        sa.Column('user_role', sa.String(length=50), nullable=True),
        sa.Column('action', sa.String(length=60), nullable=False),
        sa.Column('resource_type', sa.String(length=60), nullable=False),
        sa.Column('resource_id', sa.String(length=60), nullable=True),
        sa.Column('details', sa.Text(), nullable=True),
        sa.Column('ip_address', sa.String(length=45), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_audit_logs_clinic_id', 'audit_logs', ['clinic_id'])
    op.create_index('ix_audit_logs_user_id', 'audit_logs', ['user_id'])
    op.create_index('ix_audit_logs_action', 'audit_logs', ['action'])
    op.create_index('ix_audit_logs_resource_type', 'audit_logs', ['resource_type'])
    op.create_index('ix_audit_logs_created_at', 'audit_logs', ['created_at'])

    op.create_table(
        'payments',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('clinic_id', sa.Integer(), sa.ForeignKey('clinics.id', ondelete='CASCADE'), nullable=False),
        sa.Column('invoice_id', sa.Integer(), nullable=False),
        sa.Column('patient_id', sa.Integer(), nullable=False),
        sa.Column('amount', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('payment_method', sa.String(length=30), server_default='cash', nullable=False),
        sa.Column('payment_date', sa.Date(), server_default=sa.func.current_date(), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint('amount > 0', name='ck_payment_amount'),
        sa.ForeignKeyConstraint(
            ['clinic_id', 'invoice_id'],
            ['invoices.clinic_id', 'invoices.id'],
            name='fk_payment_invoice_clinic',
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['clinic_id', 'patient_id'],
            ['patients.clinic_id', 'patients.id'],
            name='fk_payment_patient_clinic',
            ondelete='CASCADE',
        ),
    )
    op.create_index('ix_payments_clinic_id', 'payments', ['clinic_id'])
    op.create_index('ix_payments_invoice_id', 'payments', ['invoice_id'])
    op.create_index('ix_payments_patient_id', 'payments', ['patient_id'])


def downgrade():
    op.drop_table('payments')
    op.drop_table('audit_logs')
