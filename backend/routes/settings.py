from datetime import datetime, time
from flask import Blueprint, g, jsonify, request
from sqlalchemy.exc import IntegrityError

from backend.auth import login_required, require_permission
from backend.extensions import db
from backend.services.audit import log_activity
from backend.models import (
    Appointment,
    Clinic,
    InventoryBatch,
    InventoryCategory,
    InventoryItem,
    InventoryMovement,
    InventorySupplier,
    Invoice,
    Odontogram,
    Patient,
    Prescription,
    PrescriptionMedication,
    Treatment,
    TreatmentPlan,
    XRay,
)


settings_blueprint = Blueprint("settings", __name__, url_prefix="/api")

ALLOWED_SETTING_FIELDS = frozenset(
    {
        "name",
        "phone",
        "address",
        "currency",
        "work_start",
        "work_end",
        "slot_duration",
        "inventory_expiry_warning_days",
    }
)


def _error(message, status):
    return jsonify({"error": message}), status


def _parse_time(value):
    if not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value, "%H:%M").time()
    except ValueError:
        return None


def _serialize_settings(clinic):
    return {
        "id": clinic.id,
        "name": clinic.name,
        "phone": clinic.phone or "",
        "address": clinic.address or "",
        "currency": clinic.currency or "SYR",
        "work_start": clinic.work_start.strftime("%H:%M") if clinic.work_start else "09:00",
        "work_end": clinic.work_end.strftime("%H:%M") if clinic.work_end else "18:00",
        "slot_duration": clinic.slot_duration or 30,
        "inventory_expiry_warning_days": clinic.inventory_expiry_warning_days or 60,
        "created_at": clinic.created_at.isoformat() if clinic.created_at else None,
        "updated_at": clinic.updated_at.isoformat() if clinic.updated_at else None,
    }


@settings_blueprint.get("/settings")
@login_required
@require_permission("clinic_settings.read")
def get_settings():
    clinic = g.current_clinic
    return jsonify({"data": _serialize_settings(clinic)})


@settings_blueprint.patch("/settings")
@login_required
@require_permission("clinic_settings.update")
def update_settings():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return _error("Request body must be a JSON object.", 400)

    unsupported = set(data) - ALLOWED_SETTING_FIELDS
    if unsupported:
        return _error("Unsupported settings field.", 400)

    if not data:
        return _error("At least one settings field is required.", 400)

    clinic = g.current_clinic

    if "name" in data:
        if not isinstance(data["name"], str) or not data["name"].strip():
            return _error("Clinic name must not be blank.", 422)
        if len(data["name"].strip()) > 150:
            return _error("Clinic name is too long.", 422)
        clinic.name = data["name"].strip()

    if "phone" in data:
        if data["phone"] is not None and not isinstance(data["phone"], str):
            return _error("Phone must be a string or null.", 422)
        clinic.phone = data["phone"].strip() if data["phone"] else None

    if "address" in data:
        if data["address"] is not None and not isinstance(data["address"], str):
            return _error("Address must be a string or null.", 422)
        clinic.address = data["address"].strip() if data["address"] else None

    if "currency" in data:
        if not isinstance(data["currency"], str) or not data["currency"].strip():
            return _error("Currency must not be blank.", 422)
        if len(data["currency"].strip()) > 10:
            return _error("Currency code is too long.", 422)
        clinic.currency = data["currency"].strip()

    work_start = clinic.work_start or time(9, 0)
    work_end = clinic.work_end or time(18, 0)

    if "work_start" in data:
        parsed_start = _parse_time(data["work_start"])
        if parsed_start is None:
            return _error("work_start must be in HH:MM format.", 422)
        work_start = parsed_start

    if "work_end" in data:
        parsed_end = _parse_time(data["work_end"])
        if parsed_end is None:
            return _error("work_end must be in HH:MM format.", 422)
        work_end = parsed_end

    if (work_start.hour * 60 + work_start.minute) >= (work_end.hour * 60 + work_end.minute):
        return _error("work_start must be earlier than work_end.", 422)

    clinic.work_start = work_start
    clinic.work_end = work_end

    if "slot_duration" in data:
        val = data["slot_duration"]
        if isinstance(val, bool) or not isinstance(val, int) or val <= 0 or val > 240:
            return _error("slot_duration must be a positive integer up to 240 minutes.", 422)
        clinic.slot_duration = val

    if "inventory_expiry_warning_days" in data:
        val = data["inventory_expiry_warning_days"]
        if isinstance(val, bool) or not isinstance(val, int) or val < 1 or val > 365:
            return _error("inventory_expiry_warning_days must be an integer between 1 and 365.", 422)
        clinic.inventory_expiry_warning_days = val

    try:
        log_activity(
            action="clinic_settings_updated",
            resource_type="clinic",
            resource_id=clinic.id,
            clinic_id=clinic.id,
            details={
                "name": clinic.name,
                "currency": clinic.currency,
                "slot_duration": clinic.slot_duration,
            },
        )
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return _error("Settings could not be updated.", 409)

    return jsonify({"data": _serialize_settings(clinic)})


@settings_blueprint.get("/clinic/export")
@login_required
@require_permission("clinic_settings.read")
def export_clinic_data():
    clinic_id = g.current_user.clinic_id
    clinic = g.current_clinic

    patients = db.session.scalars(
        db.select(Patient).where(Patient.clinic_id == clinic_id).order_by(Patient.id)
    ).all()
    treatments = db.session.scalars(
        db.select(Treatment).where(Treatment.clinic_id == clinic_id).order_by(Treatment.id)
    ).all()
    treatment_plans = db.session.scalars(
        db.select(TreatmentPlan).where(TreatmentPlan.clinic_id == clinic_id).order_by(TreatmentPlan.id)
    ).all()
    appointments = db.session.scalars(
        db.select(Appointment).where(Appointment.clinic_id == clinic_id).order_by(Appointment.id)
    ).all()
    prescriptions = db.session.scalars(
        db.select(Prescription).where(Prescription.clinic_id == clinic_id).order_by(Prescription.id)
    ).all()
    invoices = db.session.scalars(
        db.select(Invoice).where(Invoice.clinic_id == clinic_id).order_by(Invoice.id)
    ).all()
    odontograms = db.session.scalars(
        db.select(Odontogram).where(Odontogram.clinic_id == clinic_id).order_by(Odontogram.id)
    ).all()
    xrays = db.session.scalars(
        db.select(XRay).where(XRay.clinic_id == clinic_id).order_by(XRay.id)
    ).all()

    def _clinic_rows(model):
        return db.session.scalars(
            db.select(model).where(model.clinic_id == clinic_id).order_by(model.id)
        ).all()

    def _decimal(value):
        return format(value, "f") if value is not None else None

    inventory_export = {
        "categories": [
            {"id": c.id, "name": c.name, "is_active": c.is_active}
            for c in _clinic_rows(InventoryCategory)
        ],
        "suppliers": [
            {
                "id": s.id,
                "name": s.name,
                "contact_person": s.contact_person,
                "phone": s.phone,
                "email": s.email,
                "address": s.address,
                "notes": s.notes,
                "is_active": s.is_active,
            }
            for s in _clinic_rows(InventorySupplier)
        ],
        "items": [
            {
                "id": i.id,
                "name": i.name,
                "sku": i.sku,
                "barcode": i.barcode,
                "category_id": i.category_id,
                "supplier_id": i.supplier_id,
                "description": i.description,
                "unit": i.unit,
                "quantity": _decimal(i.quantity),
                "minimum_quantity": _decimal(i.minimum_quantity),
                "cost_per_unit": _decimal(i.cost_per_unit),
                "location": i.location,
                "track_batches": i.track_batches,
                "is_active": i.is_active,
            }
            for i in _clinic_rows(InventoryItem)
        ],
        "batches": [
            {
                "id": b.id,
                "item_id": b.item_id,
                "batch_number": b.batch_number,
                "quantity": _decimal(b.quantity),
                "unit_cost": _decimal(b.unit_cost),
                "expiry_date": b.expiry_date.isoformat() if b.expiry_date else None,
                "supplier_id": b.supplier_id,
            }
            for b in _clinic_rows(InventoryBatch)
        ],
        "movements": [
            {
                "id": m.id,
                "item_id": m.item_id,
                "batch_id": m.batch_id,
                "type": m.type,
                "quantity": _decimal(m.quantity),
                "quantity_after": _decimal(m.quantity_after),
                "unit_cost": _decimal(m.unit_cost),
                "supplier_id": m.supplier_id,
                "reference": m.reference,
                "reason": m.reason,
                "notes": m.notes,
                "reference_type": m.reference_type,
                "reference_id": m.reference_id,
                "created_by": m.created_by,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in _clinic_rows(InventoryMovement)
        ],
    }

    export_payload = {
        "clinic": _serialize_settings(clinic),
        "exported_at": datetime.now().isoformat(),
        "patients": [
            {
                "id": p.id,
                "name": p.name,
                "phone": p.phone,
                "location": p.location,
                "work_study": p.work_study,
                "dob": p.dob.isoformat() if p.dob else None,
                "gender": p.gender,
                "allergies": p.allergies,
                "medical_flags": p.medical_flags,
                "notes": p.notes,
                "created_at": p.created_at.isoformat() if p.created_at else None,
            }
            for p in patients
        ],
        "treatments": [
            {
                "id": t.id,
                "patient_id": t.patient_id,
                "tooth_number": t.tooth_number,
                "description": t.description,
                "procedure": t.procedure,
                "fee": format(t.fee, ".2f"),
                "status": t.status,
                "date": t.date.isoformat(),
            }
            for t in treatments
        ],
        "treatment_plans": [
            {
                "id": tp.id,
                "patient_id": tp.patient_id,
                "tooth_number": tp.tooth_number,
                "diagnosis": tp.diagnosis,
                "procedure": tp.procedure,
                "fee": format(tp.fee, ".2f"),
                "priority": tp.priority,
                "status": tp.status,
                "notes": tp.notes,
            }
            for tp in treatment_plans
        ],
        "appointments": [
            {
                "id": a.id,
                "patient_id": a.patient_id,
                "doctor_id": a.doctor_id,
                "date": a.date.isoformat(),
                "start_time": a.start_time.strftime("%H:%M"),
                "duration": a.duration,
                "status": a.status,
                "procedure": a.procedure,
                "notes": a.notes,
            }
            for a in appointments
        ],
        "prescriptions": [
            {
                "id": pr.id,
                "patient_id": pr.patient_id,
                "date": pr.date.isoformat(),
                "notes": pr.notes,
                "medications": [
                    {
                        "name": m.name,
                        "dosage": m.dosage,
                        "frequency": m.frequency,
                        "duration": m.duration,
                        "instructions": m.instructions,
                    }
                    for m in pr.medications
                ],
            }
            for pr in prescriptions
        ],
        "invoices": [
            {
                "id": inv.id,
                "patient_id": inv.patient_id,
                "treatment_id": inv.treatment_id,
                "amount": format(inv.amount, ".2f"),
                "discount": format(inv.discount, ".2f"),
                "paid_amount": format(inv.paid_amount, ".2f"),
                "balance": format(inv.balance, ".2f"),
                "status": inv.status,
            }
            for inv in invoices
        ],
        "odontograms": [
            {
                "id": o.id,
                "patient_id": o.patient_id,
                "tooth_number": o.tooth_number,
                "tooth_mode": o.tooth_mode,
                "condition": o.condition,
                "procedure": o.procedure,
                "notes": o.notes,
            }
            for o in odontograms
        ],
        "xrays": [
            {
                "id": x.id,
                "patient_id": x.patient_id,
                "filename": x.filename,
                "type": x.type,
                "tooth_tag": x.tooth_tag,
                "date": x.date.isoformat(),
                "notes": x.notes,
            }
            for x in xrays
        ],
        "inventory": inventory_export,
    }

    return jsonify({"data": export_payload})
