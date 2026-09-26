from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, ForeignKeyConstraint, UniqueConstraint
from backend.extensions import db


class Odontogram(db.Model):
    __tablename__ = "odontograms"

    __table_args__ = (
    UniqueConstraint(
        "clinic_id",
        "id",
        name="uq_odontogram_clinic_id",
    ),
    ForeignKeyConstraint(
        ["clinic_id", "patient_id"],
        ["patients.clinic_id", "patients.id"],
        name="fk_odontogram_patient_clinic",
        ondelete="CASCADE",
    ),
    ForeignKeyConstraint(
        ["clinic_id", "created_by"],
        ["users.clinic_id", "users.id"],
        name="fk_odontogram_created_by_clinic",
        ondelete="RESTRICT",
    ),
    UniqueConstraint(
        "patient_id",
        "tooth_number",
        "tooth_mode",
        name="uq_odontogram_patient_tooth_mode",
    ),
    CheckConstraint(
        "tooth_mode IN ('permanent', 'primary')",
        name="ck_odontogram_tooth_mode",
    ),
    CheckConstraint(
        "tooth_number >= 1 AND tooth_number <= 32",
        name="ck_odontogram_tooth_number",
    ),
)
    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    clinic_id = db.Column(
        db.Integer,
        db.ForeignKey("clinics.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    patient_id = db.Column(
        db.Integer,
        nullable=False,
        index=True,
    )

    tooth_number = db.Column(
        db.Integer,
        nullable=False,
    )

    tooth_mode = db.Column(
        db.String(20),
        nullable=False,
    )

    condition = db.Column(
        db.String(100),
        nullable=True,
    )

    procedure = db.Column(
        db.String(100),
        nullable=True,
    )

    notes = db.Column(
        db.Text,
        nullable=True,
    )

    created_by = db.Column(
        db.Integer,
        nullable=True,
        index=True,
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
        back_populates="odontograms",
    )

    patient = db.relationship(
        "Patient",
        back_populates="odontograms",
        primaryjoin="and_(Patient.clinic_id == Odontogram.clinic_id, Patient.id == Odontogram.patient_id)",
        foreign_keys="Odontogram.patient_id",
    )

    creator = db.relationship(
        "User",
        primaryjoin="and_(User.clinic_id == Odontogram.clinic_id, User.id == Odontogram.created_by)",
        foreign_keys="Odontogram.created_by",
    )