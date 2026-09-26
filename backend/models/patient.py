from datetime import datetime, timezone

from sqlalchemy import ForeignKeyConstraint, UniqueConstraint, and_
from sqlalchemy.orm import foreign

from backend.extensions import db

class Patient(db.Model):

    __tablename__ = "patients"
    __table_args__ = (
        UniqueConstraint(
            "clinic_id",
            "id",
            name="uq_patient_clinic_id",
        ),
        ForeignKeyConstraint(
            ["clinic_id", "created_by"],
            ["users.clinic_id", "users.id"],
            name="fk_patient_created_by_clinic",
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

    name = db.Column(
        db.String(200),
        nullable=False,
    )

    phone = db.Column(
        db.String(50),
        nullable=True,
        index=True,
    )

    location = db.Column(
        db.String(200),
        nullable=True,
    )

    work_study = db.Column(
        db.String(200),
        nullable=True,
    )

    dob = db.Column(
        db.Date,
        nullable=True,
    )

    gender = db.Column(
        db.String(30),
        nullable=True,
    )

    allergies = db.Column(
        db.Text,
        nullable=True,
    )

    medical_flags = db.Column(
        db.Text,
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
        back_populates="patients",
    )

    creator = db.relationship(
        "User",
        primaryjoin="and_(Patient.clinic_id == User.clinic_id, Patient.created_by == User.id)",
        foreign_keys="Patient.created_by",
    )

    odontograms = db.relationship(
        "Odontogram",
        back_populates="patient",
        primaryjoin="and_(Patient.clinic_id == Odontogram.clinic_id, Patient.id == Odontogram.patient_id)",
        foreign_keys="Odontogram.patient_id",
        cascade="all, delete-orphan",
    )

    treatments = db.relationship(
        "Treatment",
        back_populates="patient",
        primaryjoin="and_(Patient.clinic_id == Treatment.clinic_id, Patient.id == Treatment.patient_id)",
        foreign_keys="Treatment.patient_id",
        cascade="all, delete-orphan",
    )

    treatment_plans = db.relationship(
        "TreatmentPlan",
        back_populates="patient",
        primaryjoin="and_(Patient.clinic_id == TreatmentPlan.clinic_id, Patient.id == TreatmentPlan.patient_id)",
        foreign_keys="TreatmentPlan.patient_id",
        cascade="all, delete-orphan",
    )

    appointments = db.relationship(
        "Appointment",
        back_populates="patient",
        primaryjoin="and_(Patient.clinic_id == Appointment.clinic_id, Patient.id == Appointment.patient_id)",
        foreign_keys="Appointment.patient_id",
        cascade="all, delete-orphan",
    )

    prescriptions = db.relationship(
        "Prescription",
        back_populates="patient",
        primaryjoin="and_(Patient.clinic_id == Prescription.clinic_id, Patient.id == Prescription.patient_id)",
        foreign_keys="Prescription.patient_id",
        cascade="all, delete-orphan",
    )

    x_rays = db.relationship(
        "XRay",
        back_populates="patient",
        primaryjoin="and_(Patient.clinic_id == XRay.clinic_id, Patient.id == XRay.patient_id)",
        foreign_keys="XRay.patient_id",
        cascade="all, delete-orphan",
    )

    invoices = db.relationship(
        "Invoice",
        back_populates="patient",
        primaryjoin="and_(Patient.clinic_id == Invoice.clinic_id, Patient.id == Invoice.patient_id)",
        foreign_keys="Invoice.patient_id",
        cascade="all, delete-orphan",
    )
