from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKeyConstraint, UniqueConstraint

from backend.extensions import db


class Treatment(db.Model):
    __tablename__ = "treatments"

    __table_args__ = (
        CheckConstraint(
            "tooth_number IS NULL OR " "(tooth_number >= 1 AND tooth_number <= 32)",
            name="ck_treatment_tooth_number",
        ),
        CheckConstraint(
            "status IN ("
            "'planned', "
            "'accepted', "
            "'scheduled', "
            "'in-progress', "
            "'completed', "
            "'cancelled'"
            ")",
            name="ck_treatment_status",
        ),
        UniqueConstraint(
            "clinic_id",
            "id",
            name="uq_treatment_clinic_id",
        ),
        ForeignKeyConstraint(
            ["clinic_id", "patient_id"],
            ["patients.clinic_id", "patients.id"],
            name="fk_treatment_patient_clinic",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["clinic_id", "doctor_id"],
            ["users.clinic_id", "users.id"],
            name="fk_treatment_doctor_clinic",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["clinic_id", "created_by"],
            ["users.clinic_id", "users.id"],
            name="fk_treatment_created_by_clinic",
            ondelete="RESTRICT",
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

    doctor_id = db.Column(
        db.Integer,
        nullable=True,
        index=True,
    )

    created_by = db.Column(
        db.Integer,
        nullable=True,
        index=True,
    )

    tooth_number = db.Column(
        db.Integer,
        nullable=True,
    )

    status = db.Column(
        db.String(30),
        nullable=False,
        default="planned",
    )

    fee = db.Column(
        db.Numeric(12, 2),
        nullable=False,
        default=Decimal("0.00"),
    )

    description = db.Column(
        db.Text,
        nullable=True,
    )

    procedure = db.Column(
        db.String(150),
        nullable=True,
    )

    date = db.Column(
        db.Date,
        nullable=False,
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
        back_populates="treatments",
    )

    patient = db.relationship(
        "Patient",
        back_populates="treatments",
        primaryjoin="and_(Patient.clinic_id == Treatment.clinic_id, Patient.id == Treatment.patient_id)",
        foreign_keys="Treatment.patient_id",
    )

    doctor = db.relationship(
        "User",
        primaryjoin="and_(User.clinic_id == Treatment.clinic_id, User.id == Treatment.doctor_id)",
        foreign_keys="Treatment.doctor_id",
    )

    creator = db.relationship(
        "User",
        primaryjoin="and_(User.clinic_id == Treatment.clinic_id, User.id == Treatment.created_by)",
        foreign_keys="Treatment.created_by",
    )
