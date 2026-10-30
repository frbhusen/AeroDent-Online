"""link trial requests to the trial accounts they create

Revision ID: b7c8d9e0f1a2
Revises: a6b7c8d9e0f1
Create Date: 2026-10-12 18:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b7c8d9e0f1a2'
down_revision = 'a6b7c8d9e0f1'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('trial_requests', schema=None) as batch_op:
        batch_op.add_column(sa.Column('username', sa.String(length=30), nullable=True))
        batch_op.add_column(sa.Column('created_clinic_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            'fk_trial_requests_created_clinic', 'clinics', ['created_clinic_id'], ['id'], ondelete='SET NULL'
        )


def downgrade():
    with op.batch_alter_table('trial_requests', schema=None) as batch_op:
        batch_op.drop_constraint('fk_trial_requests_created_clinic', type_='foreignkey')
        batch_op.drop_column('created_clinic_id')
        batch_op.drop_column('username')
