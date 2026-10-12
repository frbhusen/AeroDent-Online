"""add odontogram billing (procedure prices, auto invoice, treatment link)

Revision ID: a6b7c8d9e0f1
Revises: f5a6b7c8d9e0
Create Date: 2026-10-12 15:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a6b7c8d9e0f1'
down_revision = 'f5a6b7c8d9e0'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('clinics', schema=None) as batch_op:
        batch_op.add_column(sa.Column('procedure_prices', sa.JSON(), nullable=True))
        batch_op.add_column(
            sa.Column('auto_invoice_odontogram', sa.Boolean(), server_default=sa.true(), nullable=False)
        )

    with op.batch_alter_table('treatments', schema=None) as batch_op:
        batch_op.add_column(sa.Column('odontogram_id', sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f('ix_treatments_odontogram_id'), ['odontogram_id'], unique=False)
        batch_op.create_foreign_key(
            'fk_treatments_odontogram_id', 'odontograms', ['odontogram_id'], ['id'], ondelete='SET NULL'
        )


def downgrade():
    with op.batch_alter_table('treatments', schema=None) as batch_op:
        batch_op.drop_constraint('fk_treatments_odontogram_id', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_treatments_odontogram_id'))
        batch_op.drop_column('odontogram_id')

    with op.batch_alter_table('clinics', schema=None) as batch_op:
        batch_op.drop_column('auto_invoice_odontogram')
        batch_op.drop_column('procedure_prices')
