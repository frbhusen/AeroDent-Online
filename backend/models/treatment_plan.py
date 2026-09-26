from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKeyConstraint, UniqueConstraint

from backend.extensions import db


class TreatmentPlan(db.Model):
    __tablename__ = "treatment_plans"

    __table_args__ = (
        CheckConstraint(
            "tooth_number IS NULL OR " "(tooth_number >= 1 AND tooth_number <= 85)",
            name="ck_treatment_plan_tooth_number",
        ),
        CheckConstraint(
            "priority IN ('low', 'medium', 'high')",
            name="ck_treatment_plan_priority",
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
            name="ck_treatment_plan_status",
        ),
        UniqueConstraint(
            "clinic_id",
            "id",
            name="uq_treatment_plan_clinic_id",
        ),
        ForeignKeyConstraint(
            ["clinic_id", "patient_id"],
            ["patients.clinic_id", "patients.id"],
            name="fk_treatment_plan_patient_clinic",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["clinic_id", "doctor_id"],
            ["users.clinic_id", "users.id"],
            name="fk_treatment_plan_doctor_clinic",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["clinic_id", "created_by"],
            ["users.clinic_id", "users.id"],
            name="fk_treatment_plan_created_by_clinic",
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

    diagnosis = db.Column(
        db.Text,
        nullable=True,
    )

    procedure = db.Column(
        db.String(150),
        nullable=True,
    )

    fee = db.Column(
        db.Numeric(12, 2),
        nullable=False,
        default=Decimal("0.00"),
    )

    priority = db.Column(
        db.String(20),
        nullable=False,
        default="medium",
    )

    status = db.Column(
        db.String(30),
        nullable=False,
        default="planned",
    )

    notes = db.Column(
        db.Text,
        nullable=True,
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
        back_populates="treatment_plans",
    )

    patient = db.relationship(
        "Patient",
        back_populates="treatment_plans",
        primaryjoin="and_(Patient.clinic_id == TreatmentPlan.clinic_id, Patient.id == TreatmentPlan.patient_id)",
        foreign_keys="TreatmentPlan.patient_id",
    )

    doctor = db.relationship(
        "User",
        primaryjoin="and_(User.clinic_id == TreatmentPlan.clinic_id, User.id == TreatmentPlan.doctor_id)",
        foreign_keys="TreatmentPlan.doctor_id",
    )

    creator = db.relationship(
        "User",
        primaryjoin="and_(User.clinic_id == TreatmentPlan.clinic_id, User.id == TreatmentPlan.created_by)",
        foreign_keys="TreatmentPlan.created_by",
    )
