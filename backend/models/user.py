from datetime import datetime, timezone

from backend.extensions import db
from sqlalchemy import CheckConstraint, UniqueConstraint

class User(db.Model):
    __tablename__ = "users"

    __table_args__ = (
        CheckConstraint(
            "role IN ('super_admin', 'head_doctor', 'doctor', 'secretary')",
            name="ck_user_role",
        ),
        UniqueConstraint(
            "clinic_id",
            "id",
            name="uq_user_clinic_id",
        ),
    )
    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    clinic_id = db.Column(
        db.Integer,
        db.ForeignKey("clinics.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    name = db.Column(
        db.String(150),
        nullable=False,
    )

    email = db.Column(
        db.String(255),
        nullable=False,
        unique=True,
        index=True,
    )

    password_hash = db.Column(
        db.String(255),
        nullable=False,
    )

    role = db.Column(
        db.String(30),
        nullable=False,
    )

    is_active = db.Column(
        db.Boolean,
        nullable=False,
        default=True,
    )

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    clinic = db.relationship(
        "Clinic",
        back_populates="users",
    )