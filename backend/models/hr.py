from datetime import date, datetime, timezone
from decimal import Decimal
from sqlalchemy import CheckConstraint, ForeignKeyConstraint
from backend.extensions import db


class StaffShift(db.Model):
    __tablename__ = "staff_shifts"

    __table_args__ = (
        CheckConstraint(
            "status IN ('scheduled', 'completed', 'absent', 'leave')",
            name="ck_staff_shift_status",
        ),
        ForeignKeyConstraint(
            ["clinic_id", "user_id"],
            ["users.clinic_id", "users.id"],
            name="fk_staff_shift_user_clinic",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["clinic_id", "created_by"],
            ["users.clinic_id", "users.id"],
            name="fk_staff_shift_created_by_clinic",
            ondelete="SET NULL",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    clinic_id = db.Column(db.Integer, db.ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = db.Column(db.Integer, nullable=False, index=True)
    date = db.Column(db.Date, nullable=False, index=True)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    shift_type = db.Column(db.String(50), nullable=False, default="regular")
    status = db.Column(db.String(30), nullable=False, default="scheduled", index=True)
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
    user = db.relationship(
        "User",
        primaryjoin="and_(User.clinic_id == StaffShift.clinic_id, User.id == StaffShift.user_id)",
        foreign_keys="StaffShift.user_id",
    )
    creator = db.relationship(
        "User",
        primaryjoin="and_(User.clinic_id == StaffShift.clinic_id, User.id == StaffShift.created_by)",
        foreign_keys="StaffShift.created_by",
    )


class TimeClock(db.Model):
    __tablename__ = "time_clocks"

    __table_args__ = (
        CheckConstraint(
            "status IN ('clocked_in', 'clocked_out')",
            name="ck_time_clock_status",
        ),
        ForeignKeyConstraint(
            ["clinic_id", "user_id"],
            ["users.clinic_id", "users.id"],
            name="fk_time_clock_user_clinic",
            ondelete="CASCADE",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    clinic_id = db.Column(db.Integer, db.ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = db.Column(db.Integer, nullable=False, index=True)
    clock_in = db.Column(db.DateTime(timezone=True), nullable=False, index=True)
    clock_out = db.Column(db.DateTime(timezone=True), nullable=True)
    total_hours = db.Column(db.Numeric(6, 2), nullable=True)
    status = db.Column(db.String(30), nullable=False, default="clocked_in", index=True)
    notes = db.Column(db.Text, nullable=True)
    ip_address = db.Column(db.String(45), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    clinic = db.relationship("Clinic")
    user = db.relationship(
        "User",
        primaryjoin="and_(User.clinic_id == TimeClock.clinic_id, User.id == TimeClock.user_id)",
        foreign_keys="TimeClock.user_id",
    )


class StaffCredential(db.Model):
    __tablename__ = "staff_credentials"

    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'expired', 'revoked')",
            name="ck_staff_credential_status",
        ),
        ForeignKeyConstraint(
            ["clinic_id", "user_id"],
            ["users.clinic_id", "users.id"],
            name="fk_staff_credential_user_clinic",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["clinic_id", "created_by"],
            ["users.clinic_id", "users.id"],
            name="fk_staff_credential_created_by_clinic",
            ondelete="SET NULL",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    clinic_id = db.Column(db.Integer, db.ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = db.Column(db.Integer, nullable=False, index=True)
    title = db.Column(db.String(150), nullable=False)
    credential_type = db.Column(db.String(50), nullable=False, default="license")
    credential_number = db.Column(db.String(100), nullable=True)
    issuing_authority = db.Column(db.String(150), nullable=True)
    issue_date = db.Column(db.Date, nullable=True)
    expiry_date = db.Column(db.Date, nullable=False, index=True)
    status = db.Column(db.String(30), nullable=False, default="active", index=True)
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
    user = db.relationship(
        "User",
        primaryjoin="and_(User.clinic_id == StaffCredential.clinic_id, User.id == StaffCredential.user_id)",
        foreign_keys="StaffCredential.user_id",
    )
    creator = db.relationship(
        "User",
        primaryjoin="and_(User.clinic_id == StaffCredential.clinic_id, User.id == StaffCredential.created_by)",
        foreign_keys="StaffCredential.created_by",
    )
