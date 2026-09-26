from datetime import datetime, date, timezone
from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKeyConstraint

from backend.extensions import db


class Payment(db.Model):
    __tablename__ = "payments"

    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_payment_amount"),
        ForeignKeyConstraint(
            ["clinic_id", "invoice_id"],
            ["invoices.clinic_id", "invoices.id"],
            name="fk_payment_invoice_clinic",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["clinic_id", "patient_id"],
            ["patients.clinic_id", "patients.id"],
            name="fk_payment_patient_clinic",
            ondelete="CASCADE",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    clinic_id = db.Column(
        db.Integer,
        db.ForeignKey("clinics.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    invoice_id = db.Column(db.Integer, nullable=False, index=True)
    patient_id = db.Column(db.Integer, nullable=False, index=True)
    amount = db.Column(db.Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    payment_method = db.Column(db.String(30), nullable=False, default="cash")
    payment_date = db.Column(db.Date, nullable=False, default=date.today)
    notes = db.Column(db.Text, nullable=True)
    created_by = db.Column(db.Integer, nullable=True)
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    invoice = db.relationship(
        "Invoice",
        primaryjoin="and_(Invoice.clinic_id == Payment.clinic_id, Invoice.id == Payment.invoice_id)",
        foreign_keys="Payment.invoice_id",
        backref=db.backref("payments", cascade="all, delete-orphan", lazy="select"),
    )
    patient = db.relationship(
        "Patient",
        primaryjoin="and_(Patient.clinic_id == Payment.clinic_id, Patient.id == Payment.patient_id)",
        foreign_keys="Payment.patient_id",
    )
