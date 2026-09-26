from datetime import datetime, timezone

from backend.extensions import db
from sqlalchemy import ForeignKeyConstraint, UniqueConstraint


class XRay(db.Model):
    __tablename__ = "x_rays"
    __table_args__ = (
        UniqueConstraint(
            "clinic_id",
            "id",
            name="uq_xray_clinic_id",
        ),
        ForeignKeyConstraint(
            ["clinic_id", "patient_id"],
            ["patients.clinic_id", "patients.id"],
            name="fk_xray_patient_clinic",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["clinic_id", "uploaded_by"],
            ["users.clinic_id", "users.id"],
            name="fk_xray_uploaded_by_clinic",
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

    uploaded_by = db.Column(
        db.Integer,
        nullable=True,
        index=True,
    )

    filename = db.Column(
        db.String(255),
        nullable=False,
    )

    storage_key = db.Column(
        db.String(500),
        nullable=False,
    )

    mime_type = db.Column(
        db.String(100),
        nullable=True,
    )

    original_mime_type = db.Column(
        db.String(100),
        nullable=True,
    )

    tooth_tag = db.Column(
        db.String(100),
        nullable=True,
    )

    type = db.Column(
        db.String(100),
        nullable=True,
    )

    date = db.Column(
        db.Date,
        nullable=False,
    )

    time = db.Column(
        db.Time,
        nullable=True,
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
        back_populates="x_rays",
    )

    patient = db.relationship(
        "Patient",
        back_populates="x_rays",
        primaryjoin="and_(Patient.clinic_id == XRay.clinic_id, Patient.id == XRay.patient_id)",
        foreign_keys="XRay.patient_id",
    )

    uploader = db.relationship(
        "User",
        primaryjoin="and_(User.clinic_id == XRay.clinic_id, User.id == XRay.uploaded_by)",
        foreign_keys="XRay.uploaded_by",
    )
