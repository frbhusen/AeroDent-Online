"""add_hr_lite_models

Revision ID: 10d4e5f6a7b8
Revises: 9c3d4e5f6a7b
Create Date: 2026-09-25 14:45:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '10d4e5f6a7b8'
down_revision = '9c3d4e5f6a7b'
branch_labels = None
depends_on = None


def upgrade():
    # 1. staff_shifts table
    op.create_table(
        'staff_shifts',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('clinic_id', sa.Integer(), sa.ForeignKey('clinics.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('start_time', sa.Time(), nullable=False),
        sa.Column('end_time', sa.Time(), nullable=False),
        sa.Column('shift_type', sa.String(length=50), server_default='regular', nullable=False),
        sa.Column('status', sa.String(length=30), server_default='scheduled', nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('scheduled', 'completed', 'absent', 'leave')", name='ck_staff_shift_status'),
        sa.ForeignKeyConstraint(
            ['clinic_id', 'user_id'],
            ['users.clinic_id', 'users.id'],
            name='fk_staff_shift_user_clinic',
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['clinic_id', 'created_by'],
            ['users.clinic_id', 'users.id'],
            name='fk_staff_shift_created_by_clinic',
            ondelete='SET NULL',
        ),
    )
    op.create_index('ix_staff_shifts_clinic_id', 'staff_shifts', ['clinic_id'])
    op.create_index('ix_staff_shifts_user_id', 'staff_shifts', ['user_id'])
    op.create_index('ix_staff_shifts_date', 'staff_shifts', ['date'])
    op.create_index('ix_staff_shifts_status', 'staff_shifts', ['status'])

    # 2. time_clocks table
    op.create_table(
        'time_clocks',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('clinic_id', sa.Integer(), sa.ForeignKey('clinics.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('clock_in', sa.DateTime(timezone=True), nullable=False),
        sa.Column('clock_out', sa.DateTime(timezone=True), nullable=True),
        sa.Column('total_hours', sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column('status', sa.String(length=30), server_default='clocked_in', nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('ip_address', sa.String(length=45), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('clocked_in', 'clocked_out')", name='ck_time_clock_status'),
        sa.ForeignKeyConstraint(
            ['clinic_id', 'user_id'],
            ['users.clinic_id', 'users.id'],
            name='fk_time_clock_user_clinic',
            ondelete='CASCADE',
        ),
    )
    op.create_index('ix_time_clocks_clinic_id', 'time_clocks', ['clinic_id'])
    op.create_index('ix_time_clocks_user_id', 'time_clocks', ['user_id'])
    op.create_index('ix_time_clocks_clock_in', 'time_clocks', ['clock_in'])
    op.create_index('ix_time_clocks_status', 'time_clocks', ['status'])

    # 3. staff_credentials table
    op.create_table(
        'staff_credentials',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('clinic_id', sa.Integer(), sa.ForeignKey('clinics.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=150), nullable=False),
        sa.Column('credential_type', sa.String(length=50), server_default='license', nullable=False),
        sa.Column('credential_number', sa.String(length=100), nullable=True),
        sa.Column('issuing_authority', sa.String(length=150), nullable=True),
        sa.Column('issue_date', sa.Date(), nullable=True),
        sa.Column('expiry_date', sa.Date(), nullable=False),
        sa.Column('status', sa.String(length=30), server_default='active', nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('active', 'expired', 'revoked')", name='ck_staff_credential_status'),
        sa.ForeignKeyConstraint(
            ['clinic_id', 'user_id'],
            ['users.clinic_id', 'users.id'],
            name='fk_staff_credential_user_clinic',
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['clinic_id', 'created_by'],
            ['users.clinic_id', 'users.id'],
            name='fk_staff_credential_created_by_clinic',
            ondelete='SET NULL',
        ),
    )
    op.create_index('ix_staff_credentials_clinic_id', 'staff_credentials', ['clinic_id'])
    op.create_index('ix_staff_credentials_user_id', 'staff_credentials', ['user_id'])
    op.create_index('ix_staff_credentials_expiry_date', 'staff_credentials', ['expiry_date'])
    op.create_index('ix_staff_credentials_status', 'staff_credentials', ['status'])


def downgrade():
    op.drop_table('staff_credentials')
    op.drop_table('time_clocks')
    op.drop_table('staff_shifts')
