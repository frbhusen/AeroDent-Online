from datetime import datetime, timezone

from backend.extensions import db
from sqlalchemy import ForeignKeyConstraint, UniqueConstraint


class Prescription(db.Model):
    __tablename__ = "prescriptions"
    __table_args__ = (
        UniqueConstraint(
            "clinic_id",
            "id",
            name="uq_prescription_clinic_id",
        ),
        ForeignKeyConstraint(
            ["clinic_id", "patient_id"],
            ["patients.clinic_id", "patients.id"],
            name="fk_prescription_patient_clinic",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["clinic_id", "doctor_id"],
            ["users.clinic_id", "users.id"],
            name="fk_prescription_doctor_clinic",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["clinic_id", "created_by"],
            ["users.clinic_id", "users.id"],
            name="fk_prescription_created_by_clinic",
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

    date = db.Column(
        db.Date,
        nullable=False,
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
        back_populates="prescriptions",
    )

    patient = db.relationship(
        "Patient",
        back_populates="prescriptions",
        primaryjoin="and_(Patient.clinic_id == Prescription.clinic_id, Patient.id == Prescription.patient_id)",
        foreign_keys="Prescription.patient_id",
    )

    doctor = db.relationship(
        "User",
        primaryjoin="and_(User.clinic_id == Prescription.clinic_id, User.id == Prescription.doctor_id)",
        foreign_keys="Prescription.doctor_id",
    )

    creator = db.relationship(
        "User",
        primaryjoin="and_(User.clinic_id == Prescription.clinic_id, User.id == Prescription.created_by)",
        foreign_keys="Prescription.created_by",
    )

    medications = db.relationship(
        "PrescriptionMedication",
        back_populates="prescription",
        cascade="all, delete-orphan",
    )


class PrescriptionMedication(db.Model):
    __tablename__ = "prescription_medications"

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    prescription_id = db.Column(
        db.Integer,
        db.ForeignKey("prescriptions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    name = db.Column(
        db.String(200),
        nullable=False,
    )

    dosage = db.Column(
        db.String(100),
        nullable=True,
    )

    frequency = db.Column(
        db.String(100),
        nullable=True,
    )

    duration = db.Column(
        db.String(100),
        nullable=True,
    )

    instructions = db.Column(
        db.Text,
        nullable=True,
    )

    prescription = db.relationship(
        "Prescription",
        back_populates="medications",
    )
