"""store_xray_images_in_db

X-ray image bytes move into PostgreSQL (xray_images), linked 1:1 to x_rays with a
clinic-scoped composite foreign key and ON DELETE CASCADE.

Existing images uploaded before this change stay on the server filesystem (x_rays.storage_key)
and keep working; `flask --app backend.app xrays import-legacy` copies them into the database.

Revision ID: e4f5a6b7c8d9
Revises: d3e4f5a6b7c8
Create Date: 2026-09-26 18:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'e4f5a6b7c8d9'
down_revision = 'd3e4f5a6b7c8'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'xray_images',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('clinic_id', sa.Integer(), sa.ForeignKey('clinics.id', ondelete='CASCADE'), nullable=False),
        sa.Column('xray_id', sa.Integer(), nullable=False),
        sa.Column('data', sa.LargeBinary(), nullable=False),
        sa.Column('mime_type', sa.String(length=100), nullable=False),
        sa.Column('image_format', sa.String(length=20), nullable=False),
        sa.Column('encoding', sa.String(length=20), nullable=False),
        sa.Column('size_bytes', sa.Integer(), nullable=False),
        sa.Column('sha256', sa.String(length=64), nullable=False),
        sa.Column('width', sa.Integer(), nullable=False),
        sa.Column('height', sa.Integer(), nullable=False),
        sa.Column('color_mode', sa.String(length=20), nullable=False),
        sa.Column('pixel_sha256', sa.String(length=64), nullable=False),
        sa.Column('original_filename', sa.String(length=255), nullable=True),
        sa.Column('original_mime_type', sa.String(length=100), nullable=True),
        sa.Column('original_size_bytes', sa.Integer(), nullable=False),
        sa.Column('original_sha256', sa.String(length=64), nullable=False),
        sa.Column('preview_data', sa.LargeBinary(), nullable=True),
        sa.Column('preview_mime_type', sa.String(length=100), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint('xray_id', name='uq_xray_image_xray'),
        sa.ForeignKeyConstraint(
            ['clinic_id', 'xray_id'],
            ['x_rays.clinic_id', 'x_rays.id'],
            name='fk_xray_image_xray_clinic',
            ondelete='CASCADE',
        ),
        sa.CheckConstraint('size_bytes > 0', name='ck_xray_image_size_positive'),
        sa.CheckConstraint(
            "encoding IN ('original', 'png-lossless', 'legacy-webp')",
            name='ck_xray_image_encoding',
        ),
    )
    op.create_index('ix_xray_images_clinic_id', 'xray_images', ['clinic_id'])
    # Image bytes are already compressed (or verified-lossless PNG). EXTERNAL stores them
    # out-of-line without PostgreSQL's pglz pass, which would only burn CPU for no gain.
    op.execute("ALTER TABLE xray_images ALTER COLUMN data SET STORAGE EXTERNAL")
    op.execute("ALTER TABLE xray_images ALTER COLUMN preview_data SET STORAGE EXTERNAL")

    op.alter_column('x_rays', 'storage_key', existing_type=sa.String(length=500), nullable=True)


def downgrade():
    # Refuse to silently discard image data that exists only in the database.
    op.execute(
        "DO $$ BEGIN IF EXISTS (SELECT 1 FROM x_rays WHERE storage_key IS NULL) THEN "
        "RAISE EXCEPTION 'Downgrade would lose X-ray images stored only in the database'; END IF; END $$;"
    )
    op.drop_table('xray_images')
    op.alter_column('x_rays', 'storage_key', existing_type=sa.String(length=500), nullable=False)
