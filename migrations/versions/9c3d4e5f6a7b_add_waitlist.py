"""add_waitlist

Revision ID: 9c3d4e5f6a7b
Revises: 8b2c3d4e5f6a
Create Date: 2026-09-25 14:35:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '9c3d4e5f6a7b'
down_revision = '8b2c3d4e5f6a'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'waitlist',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('clinic_id', sa.Integer(), sa.ForeignKey('clinics.id', ondelete='CASCADE'), nullable=False),
        sa.Column('patient_id', sa.Integer(), nullable=False),
        sa.Column('doctor_id', sa.Integer(), nullable=True),
        sa.Column('preferred_date', sa.Date(), nullable=True),
        sa.Column('preferred_time', sa.String(length=50), nullable=True),
        sa.Column('procedure', sa.String(length=150), nullable=True),
        sa.Column('priority', sa.String(length=20), server_default='normal', nullable=False),
        sa.Column('status', sa.String(length=30), server_default='waiting', nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('waiting', 'booked', 'cancelled')", name='ck_waitlist_status'),
        sa.CheckConstraint("priority IN ('normal', 'high', 'urgent')", name='ck_waitlist_priority'),
        sa.ForeignKeyConstraint(
            ['clinic_id', 'patient_id'],
            ['patients.clinic_id', 'patients.id'],
            name='fk_waitlist_patient_clinic',
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['clinic_id', 'doctor_id'],
            ['users.clinic_id', 'users.id'],
            name='fk_waitlist_doctor_clinic',
            ondelete='SET NULL',
        ),
        sa.ForeignKeyConstraint(
            ['clinic_id', 'created_by'],
            ['users.clinic_id', 'users.id'],
            name='fk_waitlist_created_by_clinic',
            ondelete='SET NULL',
        ),
    )
    op.create_index('ix_waitlist_clinic_id', 'waitlist', ['clinic_id'])
    op.create_index('ix_waitlist_patient_id', 'waitlist', ['patient_id'])
    op.create_index('ix_waitlist_doctor_id', 'waitlist', ['doctor_id'])
    op.create_index('ix_waitlist_status', 'waitlist', ['status'])


def downgrade():
    op.drop_index('ix_waitlist_status', table_name='waitlist')
    op.drop_index('ix_waitlist_doctor_id', table_name='waitlist')
    op.drop_index('ix_waitlist_patient_id', table_name='waitlist')
    op.drop_index('ix_waitlist_clinic_id', table_name='waitlist')
    op.drop_table('waitlist')
