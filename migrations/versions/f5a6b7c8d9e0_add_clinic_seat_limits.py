"""add clinic seat limits

Revision ID: f5a6b7c8d9e0
Revises: e4f5a6b7c8d9
Create Date: 2026-10-12 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f5a6b7c8d9e0'
down_revision = 'e4f5a6b7c8d9'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('clinics', schema=None) as batch_op:
        batch_op.add_column(sa.Column('max_doctors', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('max_secretaries', sa.Integer(), nullable=True))


def downgrade():
    with op.batch_alter_table('clinics', schema=None) as batch_op:
        batch_op.drop_column('max_secretaries')
        batch_op.drop_column('max_doctors')
