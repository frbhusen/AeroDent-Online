from datetime import datetime, time, timezone

from backend.extensions import db


class Clinic(db.Model):
    __tablename__ = "clinics"

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    name = db.Column(
        db.String(150),
        nullable=False,
    )

    phone = db.Column(
        db.String(50),
        nullable=True,
    )

    address = db.Column(
        db.Text,
        nullable=True,
    )

    currency = db.Column(
        db.String(10),
        nullable=False,
        default="SYR",
    )

    work_start = db.Column(
        db.Time,
        nullable=False,
        default=time(9, 0),
    )

    work_end = db.Column(
        db.Time,
        nullable=False,
        default=time(18, 0),
    )

    slot_duration = db.Column(
        db.Integer,
        nullable=False,
        default=30,
    )

    # Inventory batches expiring within this many days are flagged as "expiring soon".
    inventory_expiry_warning_days = db.Column(
        db.Integer,
        nullable=False,
        default=60,
        server_default="60",
    )

    is_active = db.Column(
        db.Boolean,
        nullable=False,
        default=True,
    )

    subscription_status = db.Column(
        db.String(30),
        nullable=False,
        default="active",
    )

    subscription_expires_at = db.Column(
        db.DateTime(timezone=True),
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

    users = db.relationship(
        "User",
        back_populates="clinic",
        cascade="all, delete-orphan",
    )

    patients = db.relationship(
        "Patient",
        back_populates="clinic",
        cascade="all, delete-orphan",
    )

    odontograms = db.relationship(
        "Odontogram",
        back_populates="clinic",
        cascade="all, delete-orphan",
    )

    treatments = db.relationship(
        "Treatment",
        back_populates="clinic",
        cascade="all, delete-orphan",
    )

    treatment_plans = db.relationship(
        "TreatmentPlan",
        back_populates="clinic",
        cascade="all, delete-orphan",
    )

    appointments = db.relationship(
        "Appointment",
        back_populates="clinic",
        cascade="all, delete-orphan",
    )

    prescriptions = db.relationship(
        "Prescription",
        back_populates="clinic",
        cascade="all, delete-orphan",
    )

    x_rays = db.relationship(
        "XRay",
        back_populates="clinic",
        cascade="all, delete-orphan",
    )

    invoices = db.relationship(
        "Invoice",
        back_populates="clinic",
        cascade="all, delete-orphan",
    )