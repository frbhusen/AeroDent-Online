from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, ForeignKeyConstraint
from backend.extensions import db


class Waitlist(db.Model):
    __tablename__ = "waitlist"

    __table_args__ = (
        CheckConstraint(
            "status IN ('waiting', 'booked', 'cancelled')",
            name="ck_waitlist_status",
        ),
        CheckConstraint(
            "priority IN ('normal', 'high', 'urgent')",
            name="ck_waitlist_priority",
        ),
        ForeignKeyConstraint(
            ["clinic_id", "patient_id"],
            ["patients.clinic_id", "patients.id"],
            name="fk_waitlist_patient_clinic",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["clinic_id", "doctor_id"],
            ["users.clinic_id", "users.id"],
            name="fk_waitlist_doctor_clinic",
            ondelete="SET NULL",
        ),
        ForeignKeyConstraint(
            ["clinic_id", "created_by"],
            ["users.clinic_id", "users.id"],
            name="fk_waitlist_created_by_clinic",
            ondelete="SET NULL",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    clinic_id = db.Column(db.Integer, db.ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False, index=True)
    patient_id = db.Column(db.Integer, nullable=False, index=True)
    doctor_id = db.Column(db.Integer, nullable=True, index=True)
    preferred_date = db.Column(db.Date, nullable=True)
    preferred_time = db.Column(db.String(50), nullable=True)
    procedure = db.Column(db.String(150), nullable=True)
    priority = db.Column(db.String(20), nullable=False, default="normal")
    status = db.Column(db.String(30), nullable=False, default="waiting", index=True)
    notes = db.Column(db.Text, nullable=True)
    created_by = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    clinic = db.relationship("Clinic")
    patient = db.relationship(
        "Patient",
        primaryjoin="and_(Patient.clinic_id == Waitlist.clinic_id, Patient.id == Waitlist.patient_id)",
        foreign_keys="Waitlist.patient_id",
    )
    doctor = db.relationship(
        "User",
        primaryjoin="and_(User.clinic_id == Waitlist.clinic_id, User.id == Waitlist.doctor_id)",
        foreign_keys="Waitlist.doctor_id",
    )
    creator = db.relationship(
        "User",
        primaryjoin="and_(User.clinic_id == Waitlist.clinic_id, User.id == Waitlist.created_by)",
        foreign_keys="Waitlist.created_by",
    )
