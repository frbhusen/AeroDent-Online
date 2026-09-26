from datetime import datetime, timezone

from backend.extensions import db


class AuditLog(db.Model):
    __tablename__ = "audit_logs"

    id = db.Column(db.Integer, primary_key=True)
    clinic_id = db.Column(
        db.Integer,
        db.ForeignKey("clinics.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    user_id = db.Column(
        db.Integer,
        nullable=True,
        index=True,
    )
    user_name = db.Column(db.String(120), nullable=True)
    user_role = db.Column(db.String(50), nullable=True)
    action = db.Column(db.String(60), nullable=False, index=True)
    resource_type = db.Column(db.String(60), nullable=False, index=True)
    resource_id = db.Column(db.String(60), nullable=True)
    details = db.Column(db.Text, nullable=True)
    ip_address = db.Column(db.String(45), nullable=True)
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )

    clinic = db.relationship("Clinic")
