from datetime import date, datetime
from decimal import Decimal

from flask import Blueprint, g, jsonify, request

from backend.auth.permissions import require_permission
from backend.auth.routes import login_required
from backend.extensions import db
from backend.models import Invoice, Payment
from backend.services.audit import log_activity


payments_blueprint = Blueprint("payments", __name__, url_prefix="/api")


@payments_blueprint.get("/invoices/<int:invoice_id>/payments")
@login_required
@require_permission("invoices.read")
def list_invoice_payments(invoice_id):
    invoice = db.session.scalar(
        db.select(Invoice).where(
            Invoice.id == invoice_id,
            Invoice.clinic_id == g.current_clinic.id,
        )
    )
    if not invoice:
        return jsonify({"error": "Invoice not found."}), 404

    payments = db.session.scalars(
        db.select(Payment)
        .where(
            Payment.invoice_id == invoice.id,
            Payment.clinic_id == g.current_clinic.id,
        )
        .order_by(Payment.payment_date.desc(), Payment.id.desc())
    ).all()

    return jsonify({
        "data": [
            {
                "id": p.id,
                "invoice_id": p.invoice_id,
                "patient_id": p.patient_id,
                "amount": float(p.amount),
                "payment_method": p.payment_method,
                "payment_date": p.payment_date.isoformat(),
                "notes": p.notes or "",
                "created_by": p.created_by,
                "created_at": p.created_at.isoformat() if p.created_at else None,
            }
            for p in payments
        ]
    })


@payments_blueprint.post("/invoices/<int:invoice_id>/payments")
@login_required
@require_permission("invoices.update")
def add_invoice_payment(invoice_id):
    invoice = db.session.scalar(
        db.select(Invoice).where(
            Invoice.id == invoice_id,
            Invoice.clinic_id == g.current_clinic.id,
        )
    )
    if not invoice:
        return jsonify({"error": "Invoice not found."}), 404

    data = request.get_json(silent=True) or {}
    try:
        amount = Decimal(str(data.get("amount", 0)))
        if not amount.is_finite():
            return jsonify({"error": "Payment amount must be a finite number."}), 400
    except Exception:
        return jsonify({"error": "Invalid payment amount."}), 400

    if amount <= 0:
        return jsonify({"error": "Payment amount must be greater than zero."}), 400

    if amount > Decimal("99999999.99"):
        return jsonify({"error": "Payment amount exceeds maximum allowable limit."}), 422

    payment_method = data.get("payment_method", "cash")
    if payment_method not in {"cash", "card", "bank_transfer", "other"}:
        payment_method = "cash"

    payment_date_val = date.today()
    if data.get("payment_date"):
        try:
            payment_date_val = datetime.strptime(data["payment_date"][:10], "%Y-%m-%d").date()
        except Exception:
            payment_date_val = date.today()

    notes = data.get("notes")

    payment = Payment(
        clinic_id=g.current_clinic.id,
        invoice_id=invoice.id,
        patient_id=invoice.patient_id,
        amount=amount,
        payment_method=payment_method,
        payment_date=payment_date_val,
        notes=notes,
        created_by=g.current_user.id,
    )
    db.session.add(payment)

    # Recalculate invoice totals
    new_paid = (invoice.paid_amount or Decimal("0.00")) + amount
    invoice.paid_amount = new_paid
    invoice.balance = max(Decimal("0.00"), invoice.amount - invoice.discount - new_paid)

    if invoice.balance <= 0:
        invoice.status = "paid"
    elif new_paid > 0:
        invoice.status = "partially-paid"

    log_activity(
        action="payment_received",
        resource_type="invoice",
        resource_id=invoice.id,
        details={
            "amount": float(amount),
            "payment_method": payment_method,
            "patient_id": invoice.patient_id,
            "new_balance": float(invoice.balance),
        },
    )

    db.session.commit()

    return jsonify({
        "payment": {
            "id": payment.id,
            "invoice_id": payment.invoice_id,
            "patient_id": payment.patient_id,
            "amount": float(payment.amount),
            "payment_method": payment.payment_method,
            "payment_date": payment.payment_date.isoformat(),
            "notes": payment.notes or "",
            "created_by": payment.created_by,
        },
        "invoice": {
            "id": invoice.id,
            "amount": float(invoice.amount),
            "paid_amount": float(invoice.paid_amount),
            "discount": float(invoice.discount),
            "balance": float(invoice.balance),
            "status": invoice.status,
        },
    }), 201


@payments_blueprint.delete("/payments/<int:payment_id>")
@login_required
@require_permission("invoices.update")
def delete_payment(payment_id):
    payment = db.session.scalar(
        db.select(Payment).where(
            Payment.id == payment_id,
            Payment.clinic_id == g.current_clinic.id,
        )
    )
    if not payment:
        return jsonify({"error": "Payment not found."}), 404

    invoice = payment.invoice
    amount = payment.amount

    db.session.delete(payment)

    # Recalculate invoice
    if invoice:
        new_paid = max(Decimal("0.00"), (invoice.paid_amount or Decimal("0.00")) - amount)
        invoice.paid_amount = new_paid
        invoice.balance = max(Decimal("0.00"), invoice.amount - invoice.discount - new_paid)
        if new_paid == 0:
            invoice.status = "unpaid"
        elif invoice.balance <= 0:
            invoice.status = "paid"
        else:
            invoice.status = "partially-paid"

    log_activity(
        action="payment_voided",
        resource_type="payment",
        resource_id=payment_id,
        details={"amount": float(amount), "invoice_id": invoice.id if invoice else None},
    )

    db.session.commit()
    return jsonify({"message": "Payment voided successfully."})
