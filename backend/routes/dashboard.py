from datetime import date
from decimal import Decimal

from flask import Blueprint, g, jsonify
from sqlalchemy import func

from backend.auth import login_required, require_permission
from backend.extensions import db
from backend.models import Appointment, Invoice, Patient, User


dashboard_blueprint = Blueprint("dashboard", __name__, url_prefix="/api/dashboard")


def _error(message, status):
    return jsonify({"error": message}), status


@dashboard_blueprint.get("")
@login_required
@require_permission("dashboard.read")
def get_dashboard_summary():
    clinic_id = g.current_user.clinic_id
    today = date.today()

    active_patients_count = db.session.scalar(
        db.select(func.count(Patient.id)).where(Patient.clinic_id == clinic_id)
    ) or 0

    upcoming_appointments_count = db.session.scalar(
        db.select(func.count(Appointment.id)).where(
            Appointment.clinic_id == clinic_id,
            Appointment.date >= today,
            Appointment.status != "cancelled",
        )
    ) or 0

    outstanding_balance = db.session.scalar(
        db.select(func.coalesce(func.sum(Invoice.balance), Decimal("0.00"))).where(
            Invoice.clinic_id == clinic_id,
            Invoice.status.in_(["unpaid", "partially-paid"]),
        )
    ) or Decimal("0.00")

    upcoming_appointments = (
        db.session.execute(
            db.select(
                Appointment.id,
                Appointment.patient_id,
                Patient.name.label("patient_name"),
                Appointment.doctor_id,
                User.name.label("doctor_name"),
                Appointment.date,
                Appointment.start_time,
                Appointment.duration,
                Appointment.procedure,
                Appointment.status,
            )
            .join(Patient, Appointment.patient_id == Patient.id)
            .outerjoin(User, Appointment.doctor_id == User.id)
            .where(
                Appointment.clinic_id == clinic_id,
                Appointment.date >= today,
                Appointment.status != "cancelled",
            )
            .order_by(Appointment.date.asc(), Appointment.start_time.asc())
            .limit(5)
        )
        .mappings()
        .all()
    )

    recent_patients = db.session.scalars(
        db.select(Patient)
        .where(Patient.clinic_id == clinic_id)
        .order_by(Patient.id.desc())
        .limit(5)
    ).all()

    return jsonify(
        {
            "data": {
                "active_patients_count": active_patients_count,
                "upcoming_appointments_count": upcoming_appointments_count,
                "outstanding_balance": format(outstanding_balance, ".2f"),
                "upcoming_appointments": [
                    {
                        "id": row["id"],
                        "patient_id": row["patient_id"],
                        "patient_name": row["patient_name"],
                        "doctor_id": row["doctor_id"],
                        "doctor_name": row["doctor_name"],
                        "date": row["date"].isoformat(),
                        "start_time": row["start_time"].strftime("%H:%M"),
                        "duration": row["duration"],
                        "procedure": row["procedure"],
                        "status": row["status"],
                    }
                    for row in upcoming_appointments
                ],
                "recent_patients": [
                    {
                        "id": p.id,
                        "name": p.name,
                        "phone": p.phone,
                        "allergies": p.allergies,
                        "medical_flags": p.medical_flags,
                        "created_at": p.created_at.isoformat() if p.created_at else None,
                    }
                    for p in recent_patients
                ],
            }
        }
    )
