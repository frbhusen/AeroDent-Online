from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKeyConstraint, UniqueConstraint

from backend.extensions import db


class Invoice(db.Model):
    __tablename__ = "invoices"

    __table_args__ = (
        CheckConstraint(
            "amount >= 0",
            name="ck_invoice_amount",
        ),
        CheckConstraint(
            "paid_amount >= 0",
            name="ck_invoice_paid_amount",
        ),
        CheckConstraint(
            "discount >= 0",
            name="ck_invoice_discount",
        ),
        CheckConstraint(
            "status IN ('unpaid', 'partially-paid', 'paid', 'cancelled')",
            name="ck_invoice_status",
        ),
        UniqueConstraint(
            "clinic_id",
            "id",
            name="uq_invoice_clinic_id",
        ),
        ForeignKeyConstraint(
            ["clinic_id", "patient_id"],
            ["patients.clinic_id", "patients.id"],
            name="fk_invoice_patient_clinic",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["clinic_id", "treatment_id"],
            ["treatments.clinic_id", "treatments.id"],
            name="fk_invoice_treatment_clinic",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["clinic_id", "created_by"],
            ["users.clinic_id", "users.id"],
            name="fk_invoice_created_by_clinic",
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

    treatment_id = db.Column(
        db.Integer,
        nullable=True,
        index=True,
    )

    amount = db.Column(
        db.Numeric(12, 2),
        nullable=False,
        default=Decimal("0.00"),
    )

    paid_amount = db.Column(
        db.Numeric(12, 2),
        nullable=False,
        default=Decimal("0.00"),
    )

    discount = db.Column(
        db.Numeric(12, 2),
        nullable=False,
        default=Decimal("0.00"),
    )

    balance = db.Column(
        db.Numeric(12, 2),
        nullable=False,
        default=Decimal("0.00"),
    )

    status = db.Column(
        db.String(30),
        nullable=False,
        default="unpaid",
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
        back_populates="invoices",
    )

    patient = db.relationship(
        "Patient",
        back_populates="invoices",
        primaryjoin="and_(Patient.clinic_id == Invoice.clinic_id, Patient.id == Invoice.patient_id)",
        foreign_keys="Invoice.patient_id",
    )

    treatment = db.relationship(
        "Treatment",
        primaryjoin="and_(Treatment.clinic_id == Invoice.clinic_id, Treatment.id == Invoice.treatment_id)",
        foreign_keys="Invoice.treatment_id",
    )

    creator = db.relationship(
        "User",
        primaryjoin="and_(User.clinic_id == Invoice.clinic_id, User.id == Invoice.created_by)",
        foreign_keys="Invoice.created_by",
    )
