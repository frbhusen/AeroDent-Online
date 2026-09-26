"""add_clinic_subscriptions_and_super_admin

Revision ID: 6f2f3385d0ef
Revises: 647b6203aff5
Create Date: 2026-09-24 21:21:08.400649

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '6f2f3385d0ef'
down_revision = '647b6203aff5'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('clinics', schema=None) as batch_op:
        batch_op.add_column(sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')))
        batch_op.add_column(sa.Column('subscription_status', sa.String(length=30), nullable=False, server_default='active'))
        batch_op.add_column(sa.Column('subscription_expires_at', sa.DateTime(timezone=True), nullable=True))

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.alter_column('clinic_id',
               existing_type=sa.INTEGER(),
               nullable=True)

    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS ck_user_role;")
    op.execute("ALTER TABLE users ADD CONSTRAINT ck_user_role CHECK (role IN ('super_admin', 'head_doctor', 'doctor', 'secretary'));")


def downgrade():
    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS ck_user_role;")
    op.execute("ALTER TABLE users ADD CONSTRAINT ck_user_role CHECK (role IN ('head_doctor', 'doctor', 'secretary'));")

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.alter_column('clinic_id',
               existing_type=sa.INTEGER(),
               nullable=False)

    with op.batch_alter_table('clinics', schema=None) as batch_op:
        batch_op.drop_column('subscription_expires_at')
        batch_op.drop_column('subscription_status')
        batch_op.drop_column('is_active')
