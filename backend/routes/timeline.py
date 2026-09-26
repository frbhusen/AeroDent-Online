from flask import Blueprint, g, jsonify
from sqlalchemy.orm import selectinload

from backend.auth import login_required, require_permission
from backend.extensions import db
from backend.models import (
    Appointment,
    Patient,
    Prescription,
    Treatment,
    TreatmentPlan,
    XRay,
)


timeline_blueprint = Blueprint("timeline", __name__, url_prefix="/api/patients")


def _error(message, status):
    return jsonify({"error": message}), status


def _scoped_patient(patient_id):
    return db.session.scalar(
        db.select(Patient).where(
            Patient.id == patient_id,
            Patient.clinic_id == g.current_user.clinic_id,
        )
    )


@timeline_blueprint.get("/<int:patient_id>/timeline")
@login_required
@require_permission("patients.read")
def get_patient_timeline(patient_id):
    patient = _scoped_patient(patient_id)
    if patient is None:
        return _error("Patient not found.", 404)

    clinic_id = g.current_user.clinic_id
    events = []

    # Appointments
    appointments = db.session.scalars(
        db.select(Appointment).where(
            Appointment.patient_id == patient.id,
            Appointment.clinic_id == clinic_id,
        )
    ).all()
    for appt in appointments:
        start_str = appt.start_time.strftime("%H:%M") if appt.start_time else ""
        events.append(
            {
                "type": "appointment",
                "id": appt.id,
                "date": appt.date.isoformat(),
                "time": start_str,
                "title": appt.procedure or "Appointment",
                "description": f"{start_str} · {appt.status}",
                "icon": "📅",
                "status": appt.status,
            }
        )

    # Treatments
    treatments = db.session.scalars(
        db.select(Treatment).where(
            Treatment.patient_id == patient.id,
            Treatment.clinic_id == clinic_id,
        )
    ).all()
    for tr in treatments:
        tooth_str = f"#{tr.tooth_number} · " if tr.tooth_number else ""
        events.append(
            {
                "type": "treatment",
                "id": tr.id,
                "date": tr.date.isoformat(),
                "time": "",
                "title": tr.description or "Treatment",
                "description": f"{tooth_str}{format(tr.fee, '.2f')}",
                "icon": "🦷",
                "status": tr.status,
            }
        )

    # Treatment Plans
    plans = db.session.scalars(
        db.select(TreatmentPlan).where(
            TreatmentPlan.patient_id == patient.id,
            TreatmentPlan.clinic_id == clinic_id,
        )
    ).all()
    for plan in plans:
        date_val = plan.updated_at or plan.created_at
        date_str = date_val.date().isoformat() if date_val else ""
        tooth_str = f"#{plan.tooth_number} · " if plan.tooth_number else ""
        events.append(
            {
                "type": "treatment-plan",
                "id": plan.id,
                "date": date_str,
                "time": "",
                "title": plan.procedure or "Treatment Plan",
                "description": f"{tooth_str}Diagnosis: {plan.diagnosis or '—'}",
                "icon": "📋",
                "status": plan.status,
            }
        )

    # Prescriptions
    prescriptions = db.session.scalars(
        db.select(Prescription)
        .options(selectinload(getattr(Prescription, "medications")))
        .where(
            Prescription.patient_id == patient.id,
            Prescription.clinic_id == clinic_id,
        )
    ).all()
    for rx in prescriptions:
        med_names = [m.name for m in rx.medications]
        events.append(
            {
                "type": "prescription",
                "id": rx.id,
                "date": rx.date.isoformat(),
                "time": "",
                "title": "Prescription",
                "description": ", ".join(med_names) if med_names else "Medication",
                "icon": "💊",
                "status": "",
            }
        )

    # X-Rays
    xrays = db.session.scalars(
        db.select(XRay).where(
            XRay.patient_id == patient.id,
            XRay.clinic_id == clinic_id,
        )
    ).all()
    for xray in xrays:
        tooth_tag_str = f" · Tooth #{xray.tooth_tag}" if xray.tooth_tag else ""
        events.append(
            {
                "type": "xray",
                "id": xray.id,
                "date": xray.date.isoformat(),
                "time": xray.time.strftime("%H:%M") if xray.time else "",
                "title": xray.filename or "X-ray",
                "description": f"{xray.type}{tooth_tag_str}",
                "icon": "📷",
                "status": "",
                "image_url": f"/api/x-rays/{xray.id}/file",
            }
        )

    # Sort descending by date and time
    events.sort(
        key=lambda ev: f"{ev.get('date', '')} {ev.get('time', '')}".strip(),
        reverse=True,
    )

    return jsonify({"data": events})
