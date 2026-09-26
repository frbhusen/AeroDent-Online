from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, ForeignKeyConstraint, UniqueConstraint
from sqlalchemy.orm import deferred

from backend.extensions import db


class XRayImage(db.Model):
    """
    Server-owned X-ray image bytes, stored in PostgreSQL next to their X-ray record.

    * One row per X-ray (``xray_id`` unique), bound to the same clinic by a composite foreign
      key with ON DELETE CASCADE: the record and its image are created and deleted in one
      transaction, so neither can exist without the other.
    * ``data`` holds either the untouched original upload (``encoding='original'``) or a
      verified pixel-identical PNG re-encoding (``encoding='png-lossless'``). Nothing is ever
      stored lossily; ``legacy-webp`` marks images migrated from the old (lossy) pipeline.
    * ``preview_data`` is an optional display-only rendition for formats browsers cannot show
      (e.g. some TIFFs). Downloads always return ``data``.
    * The byte columns are deferred so listing X-rays never loads image data.
    """

    __tablename__ = "xray_images"
    __table_args__ = (
        UniqueConstraint("xray_id", name="uq_xray_image_xray"),
        ForeignKeyConstraint(
            ["clinic_id", "xray_id"],
            ["x_rays.clinic_id", "x_rays.id"],
            name="fk_xray_image_xray_clinic",
            ondelete="CASCADE",
        ),
        CheckConstraint("size_bytes > 0", name="ck_xray_image_size_positive"),
        CheckConstraint(
            "encoding IN ('original', 'png-lossless', 'legacy-webp')",
            name="ck_xray_image_encoding",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    clinic_id = db.Column(db.Integer, db.ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False, index=True)
    xray_id = db.Column(db.Integer, nullable=False)

    data = deferred(db.Column(db.LargeBinary, nullable=False))
    mime_type = db.Column(db.String(100), nullable=False)
    image_format = db.Column(db.String(20), nullable=False)
    encoding = db.Column(db.String(20), nullable=False)
    size_bytes = db.Column(db.Integer, nullable=False)
    sha256 = db.Column(db.String(64), nullable=False)

    width = db.Column(db.Integer, nullable=False)
    height = db.Column(db.Integer, nullable=False)
    color_mode = db.Column(db.String(20), nullable=False)
    # SHA-256 of the decoded pixels (mode, size and raw bytes): proves that a re-encoded PNG
    # is pixel-identical to the upload, and detects corruption on later verification.
    pixel_sha256 = db.Column(db.String(64), nullable=False)

    original_filename = db.Column(db.String(255), nullable=True)
    original_mime_type = db.Column(db.String(100), nullable=True)
    original_size_bytes = db.Column(db.Integer, nullable=False)
    original_sha256 = db.Column(db.String(64), nullable=False)

    preview_data = deferred(db.Column(db.LargeBinary, nullable=True))
    preview_mime_type = db.Column(db.String(100), nullable=True)

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
