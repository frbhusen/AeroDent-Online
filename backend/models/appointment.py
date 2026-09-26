from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, ForeignKeyConstraint, UniqueConstraint

from backend.extensions import db


class Appointment(db.Model):
    __tablename__ = "appointments"

    __table_args__ = (
        CheckConstraint(
            "duration > 0",
            name="ck_appointment_duration",
        ),
        CheckConstraint(
            "status IN ('booked', 'arrived', 'in_chair', 'completed', 'cancelled')",
            name="ck_appointment_status",
        ),
        UniqueConstraint(
            "clinic_id",
            "id",
            name="uq_appointment_clinic_id",
        ),
        ForeignKeyConstraint(
            ["clinic_id", "patient_id"],
            ["patients.clinic_id", "patients.id"],
            name="fk_appointment_patient_clinic",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["clinic_id", "doctor_id"],
            ["users.clinic_id", "users.id"],
            name="fk_appointment_doctor_clinic",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["clinic_id", "created_by"],
            ["users.clinic_id", "users.id"],
            name="fk_appointment_created_by_clinic",
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
        index=True,
    )

    start_time = db.Column(
        db.Time,
        nullable=False,
    )

    duration = db.Column(
        db.Integer,
        nullable=False,
    )

    status = db.Column(
        db.String(30),
        nullable=False,
        default="booked",
    )

    procedure = db.Column(
        db.String(150),
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
        back_populates="appointments",
    )

    patient = db.relationship(
        "Patient",
        back_populates="appointments",
        primaryjoin="and_(Patient.clinic_id == Appointment.clinic_id, Patient.id == Appointment.patient_id)",
        foreign_keys="Appointment.patient_id",
    )

    doctor = db.relationship(
        "User",
        primaryjoin="and_(User.clinic_id == Appointment.clinic_id, User.id == Appointment.doctor_id)",
        foreign_keys="Appointment.doctor_id",
    )

    creator = db.relationship(
        "User",
        primaryjoin="and_(User.clinic_id == Appointment.clinic_id, User.id == Appointment.created_by)",
        foreign_keys="Appointment.created_by",
    )
