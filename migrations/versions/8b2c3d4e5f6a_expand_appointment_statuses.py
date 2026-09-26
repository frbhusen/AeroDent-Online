"""expand_appointment_statuses

Revision ID: 8b2c3d4e5f6a
Revises: 7a1b2c3d4e5f
Create Date: 2026-09-24 22:00:00.000000

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = '8b2c3d4e5f6a'
down_revision = '7a1b2c3d4e5f'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('appointments', schema=None) as batch_op:
        batch_op.drop_constraint('ck_appointment_status', type_='check')
        batch_op.create_check_constraint(
            'ck_appointment_status',
            "status IN ('booked', 'arrived', 'in_chair', 'completed', 'cancelled')"
        )


def downgrade():
    with op.batch_alter_table('appointments', schema=None) as batch_op:
        batch_op.drop_constraint('ck_appointment_status', type_='check')
        batch_op.create_check_constraint(
            'ck_appointment_status',
            "status IN ('booked', 'completed', 'cancelled')"
        )
