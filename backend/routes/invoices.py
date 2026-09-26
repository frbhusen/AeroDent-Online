from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from flask import Blueprint, g, jsonify, request
from sqlalchemy.exc import IntegrityError

from backend.auth import login_required, require_permission
from backend.extensions import db
from backend.models import Invoice, Patient, Treatment
from backend.services.audit import log_activity
from backend.services.validation import query_int, query_page


invoices_blueprint = Blueprint("invoices", __name__, url_prefix="/api/invoices")

INVOICE_FIELDS = frozenset(
    {"patient_id", "treatment_id", "amount", "discount", "paid_amount", "status"}
)
INVOICE_INTERNAL_FIELDS = frozenset(
    {"id", "clinic_id", "created_by", "created_at", "updated_at", "balance"}
)
INVOICE_STATUSES = frozenset({"unpaid", "partially-paid", "paid", "cancelled"})
MONEY_QUANTUM = Decimal("0.01")
DEFAULT_PER_PAGE = 25
MAX_PER_PAGE = 100


def _error(message, status):
    return jsonify({"error": message}), status


def _json_object():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return None, _error("Request body must be a JSON object.", 400)
    unsupported = set(data) - INVOICE_FIELDS
    if unsupported:
        if unsupported & INVOICE_INTERNAL_FIELDS:
            return None, _error("Invoice ownership and balance are server-controlled.", 400)
        return None, _error("Unsupported invoice field.", 400)
    return data, None


def _money(value, field):
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None, _error(f"{field} must be a valid non-negative amount.", 422)
    if not parsed.is_finite() or parsed < 0:
        return None, _error(f"{field} must be a valid non-negative amount.", 422)
    if parsed > Decimal("99999999.99"):
        return None, _error(f"{field} exceeds maximum allowable amount.", 422)
    return parsed.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP), None


def _scoped_invoice(invoice_id):
    return db.session.scalar(
        db.select(Invoice).where(
            Invoice.id == invoice_id,
            Invoice.clinic_id == g.current_user.clinic_id,
        )
    )


def _scoped_patient(patient_id):
    return db.session.scalar(
        db.select(Patient).where(
            Patient.id == patient_id,
            Patient.clinic_id == g.current_user.clinic_id,
        )
    )


def _scoped_treatment(treatment_id):
    return db.session.scalar(
        db.select(Treatment).where(
            Treatment.id == treatment_id,
            Treatment.clinic_id == g.current_user.clinic_id,
        )
    )


def _validate_references(patient_id, treatment_id):
    patient = _scoped_patient(patient_id)
    if patient is None:
        return _error("Patient not found.", 404)
    if treatment_id is not None:
        treatment = _scoped_treatment(treatment_id)
        if treatment is None:
            return _error("Treatment not found.", 404)
        if treatment.patient_id != patient.id:
            return _error("Treatment does not belong to the selected patient.", 400)
    return None


def _financial_values(data, existing=None):
    amount = data.get("amount", existing.amount if existing else None)
    discount = data.get("discount", existing.discount if existing else Decimal("0.00"))
    paid_amount = data.get("paid_amount", existing.paid_amount if existing else Decimal("0.00"))
    if amount is None:
        return None, _error("amount is required.", 422)
    amount, error = _money(amount, "amount")
    if error or amount is None:
        return None, error or _error("amount is required.", 422)
    discount, error = _money(discount, "discount")
    if error or discount is None:
        return None, error or _error("discount is invalid.", 422)
    paid_amount, error = _money(paid_amount, "paid_amount")
    if error or paid_amount is None:
        return None, error or _error("paid_amount is invalid.", 422)
    if discount > amount:
        return None, _error("discount cannot exceed amount.", 422)
    payable = amount - discount
    if paid_amount > payable:
        return None, _error("paid_amount cannot exceed the payable amount.", 422)
    balance = payable - paid_amount
    requested_status = data.get("status", existing.status if existing else None)
    if requested_status is not None and (not isinstance(requested_status, str) or requested_status not in INVOICE_STATUSES):
        return None, _error("Invalid invoice status.", 400)
    if requested_status == "cancelled":
        status = "cancelled"
    elif balance == payable:
        status = "unpaid"
    elif balance == Decimal("0.00"):
        status = "paid"
    else:
        status = "partially-paid"
    return {
        "amount": amount,
        "discount": discount,
        "paid_amount": paid_amount,
        "balance": balance,
        "status": status,
    }, None


def _serialize_invoice(invoice):
    return {
        "id": invoice.id,
        "clinic_id": invoice.clinic_id,
        "patient_id": invoice.patient_id,
        "treatment_id": invoice.treatment_id,
        "amount": format(invoice.amount, ".2f"),
        "discount": format(invoice.discount, ".2f"),
        "paid_amount": format(invoice.paid_amount, ".2f"),
        "balance": format(invoice.balance, ".2f"),
        "status": invoice.status,
        "created_by": invoice.created_by,
        "created_at": invoice.created_at.isoformat() if invoice.created_at else None,
        "updated_at": invoice.updated_at.isoformat() if invoice.updated_at else None,
    }


@invoices_blueprint.get("")
@login_required
@require_permission("invoices.read")
def list_invoices():
    query = db.select(Invoice).where(Invoice.clinic_id == g.current_user.clinic_id)
    for field, model_field in (
        ("patient_id", Invoice.patient_id),
        ("treatment_id", Invoice.treatment_id),
    ):
        if field in request.args:
            try:
                value = query_int(request.args[field])
            except ValueError:
                return _error(f"{field} must be a positive integer.", 400)
            if value <= 0:
                return _error(f"{field} must be a positive integer.", 400)
            query = query.where(model_field == value)
    if "status" in request.args:
        if request.args["status"] not in INVOICE_STATUSES:
            return _error("Invalid invoice status.", 400)
        query = query.where(Invoice.status == request.args["status"])
    try:
        page = max(query_page(request.args.get("page", 1)), 1)
        per_page = min(max(query_int(request.args.get("per_page", DEFAULT_PER_PAGE)), 1), MAX_PER_PAGE)
    except ValueError:
        return _error("page and per_page must be positive integers.", 400)
    total = db.session.scalar(db.select(db.func.count()).select_from(query.subquery()))
    pages = (total + per_page - 1) // per_page if total else 0
    invoices = db.session.scalars(
        query.order_by(Invoice.id.desc()).offset((page - 1) * per_page).limit(per_page)
    ).all()
    return jsonify({
        "data": [_serialize_invoice(invoice) for invoice in invoices],
        "meta": {"page": page, "per_page": per_page, "total": total, "pages": pages},
    })


@invoices_blueprint.get("/<int:invoice_id>")
@login_required
@require_permission("invoices.read")
def get_invoice(invoice_id):
    invoice = _scoped_invoice(invoice_id)
    if invoice is None:
        return _error("Invoice not found.", 404)
    return jsonify({"data": _serialize_invoice(invoice)})


@invoices_blueprint.post("")
@login_required
@require_permission("invoices.create")
def create_invoice():
    data, error = _json_object()
    if error:
        return error
    if "patient_id" not in data:
        return _error("patient_id is required.", 422)
    for field in ("patient_id", "treatment_id"):
        if field in data and data[field] is not None and (
            isinstance(data[field], bool) or not isinstance(data[field], int) or data[field] <= 0
        ):
            return _error(f"{field} must be a positive integer.", 422)
    error = _validate_references(data["patient_id"], data.get("treatment_id"))
    if error:
        return error
    financial, error = _financial_values(data)
    if error:
        return error
    invoice = Invoice(
        patient_id=data["patient_id"],
        treatment_id=data.get("treatment_id"),
        **financial,
        clinic_id=g.current_user.clinic_id,
        created_by=g.current_user.id,
    )
    db.session.add(invoice)
    try:
        db.session.flush()
        log_activity(
            action="invoice_created",
            resource_type="invoice",
            resource_id=invoice.id,
            details={"patient_id": invoice.patient_id, "amount": float(invoice.amount)},
        )
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return _error("Invoice could not be created.", 409)
    return jsonify({"data": _serialize_invoice(invoice)}), 201


@invoices_blueprint.patch("/<int:invoice_id>")
@login_required
@require_permission("invoices.update")
def update_invoice(invoice_id):
    invoice = _scoped_invoice(invoice_id)
    if invoice is None:
        return _error("Invoice not found.", 404)
    data, error = _json_object()
    if error:
        return error
    patient_id = data.get("patient_id", invoice.patient_id)
    treatment_id = data.get("treatment_id", invoice.treatment_id)
    for field, value in (("patient_id", patient_id), ("treatment_id", treatment_id)):
        if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value <= 0):
            return _error(f"{field} must be a positive integer.", 422)
    error = _validate_references(patient_id, treatment_id)
    if error:
        return error
    financial, error = _financial_values(data, invoice)
    if error:
        return error
    invoice.patient_id = patient_id
    invoice.treatment_id = treatment_id
    for field, value in financial.items():
        setattr(invoice, field, value)
    try:
        log_activity(
            action="invoice_updated",
            resource_type="invoice",
            resource_id=invoice.id,
            details={"amount": float(invoice.amount), "status": invoice.status},
        )
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return _error("Invoice could not be updated.", 409)
    return jsonify({"data": _serialize_invoice(invoice)})


@invoices_blueprint.delete("/<int:invoice_id>")
@login_required
@require_permission("invoices.delete")
def delete_invoice(invoice_id):
    invoice = _scoped_invoice(invoice_id)
    if invoice is None:
        return _error("Invoice not found.", 404)
    deleted_patient_id = invoice.patient_id
    deleted_amount = float(invoice.amount)

    db.session.delete(invoice)
    try:
        log_activity(
            action="invoice_deleted",
            resource_type="invoice",
            resource_id=invoice_id,
            details={"patient_id": deleted_patient_id, "amount": deleted_amount},
        )
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return _error("Invoice could not be deleted.", 409)
    return "", 204