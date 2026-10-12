"""Keeps Treatments and Invoices in step with tooth changes made in the odontogram.

Only procedures are billed (``BILLABLE_CONDITIONS``); "decay"/"healthy" are findings, not work done.
A generated treatment is linked to its odontogram row through ``Treatment.odontogram_id`` so a later
change to the same tooth updates it instead of billing twice. Once money has been paid against the
invoice the record is left alone and a new treatment is created for the new work.
"""

from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from backend.auth.permissions import user_has_permission
from backend.extensions import db
from backend.models import Invoice, Treatment

BILLABLE_CONDITIONS = ("filling", "crown", "rct", "extract", "implant")
PROCEDURE_LABELS = {
    "filling": "Filling",
    "crown": "Crown",
    "rct": "Root canal treatment",
    "extract": "Extraction",
    "implant": "Implant",
}
MONEY_QUANTUM = Decimal("0.01")
MAX_FEE = Decimal("99999999.99")


def parse_money(value):
    """Returns (Decimal, None) or (None, error message). None/"" -> (None, None) meaning "not given"."""
    if value is None or value == "":
        return None, None
    if isinstance(value, bool):
        return None, "Fee must be a valid non-negative amount."
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None, "Fee must be a valid non-negative amount."
    if not parsed.is_finite() or parsed < 0 or parsed > MAX_FEE:
        return None, "Fee must be a valid non-negative amount."
    return parsed.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP), None


def normalize_prices(raw):
    """Validates the clinic price list. Returns (dict, None) or (None, error message)."""
    if raw is None:
        return None, None
    if not isinstance(raw, dict):
        return None, "procedure_prices must be an object."
    unsupported = set(raw) - set(BILLABLE_CONDITIONS)
    if unsupported:
        return None, "Unsupported procedure in procedure_prices."
    prices = {}
    for key, value in raw.items():
        price, error = parse_money(value)
        if error:
            return None, error
        if price is not None:
            prices[key] = format(price, ".2f")
    return prices, None


def clinic_prices(clinic):
    prices = clinic.procedure_prices if isinstance(clinic.procedure_prices, dict) else {}
    return {key: prices.get(key) for key in BILLABLE_CONDITIONS if prices.get(key) is not None}


def _treatment_text(record):
    label = PROCEDURE_LABELS[record.condition]
    if record.tooth_mode == "primary":
        return label, f"{label} - primary tooth {chr(64 + record.tooth_number)}"
    return label, label


def _linked_treatment(record):
    return db.session.scalar(
        db.select(Treatment)
        .where(
            Treatment.clinic_id == record.clinic_id,
            Treatment.odontogram_id == record.id,
            Treatment.status != "cancelled",
        )
        .order_by(Treatment.id.desc())
    )


def _invoices_for(treatment):
    return db.session.scalars(
        db.select(Invoice).where(
            Invoice.clinic_id == treatment.clinic_id,
            Invoice.treatment_id == treatment.id,
            Invoice.status != "cancelled",
        )
    ).all()


def _is_settled(invoices):
    """True once any money has been paid, i.e. the record must no longer be rewritten."""
    return any(invoice.paid_amount > 0 for invoice in invoices)


def _reprice(invoice, fee):
    invoice.amount = fee
    invoice.discount = min(invoice.discount, fee)
    invoice.balance = fee - invoice.discount - invoice.paid_amount
    invoice.status = "unpaid"


def sync_billing(clinic, user, record, previous_condition, fee=None, create_invoice=None):
    """Create/update/cancel the treatment (and invoice) matching the tooth's new condition.

    ``record`` is the odontogram row *after* the change (``record.condition`` is the new value, or
    ``None``/"clear" semantics are expressed by passing ``record.condition = None`` for deletions).
    Returns a small summary dict for the API response, or None when nothing was touched.
    """
    new_condition = record.condition
    if new_condition == previous_condition:
        return None
    if not user_has_permission(user, "treatments.create"):
        return None

    linked = _linked_treatment(record)

    if new_condition not in BILLABLE_CONDITIONS:
        # Procedure undone / downgraded to a finding: void the unpaid billing it created.
        if linked is None:
            return None
        invoices = _invoices_for(linked)
        linked.odontogram_id = None
        if _is_settled(invoices):
            return {"action": "kept", "treatment_id": linked.id, "invoice_id": None}
        linked.status = "cancelled"
        for invoice in invoices:
            invoice.status = "cancelled"
            invoice.balance = Decimal("0.00")
        return {"action": "cancelled", "treatment_id": linked.id, "invoice_id": None}

    if fee is None:
        default_price = clinic_prices(clinic).get(new_condition)
        fee = Decimal(default_price) if default_price is not None else Decimal("0.00")

    procedure, description = _treatment_text(record)
    tooth_number = record.tooth_number if record.tooth_mode == "permanent" else None
    want_invoice = clinic.auto_invoice_odontogram if create_invoice is None else bool(create_invoice)
    want_invoice = want_invoice and user_has_permission(user, "invoices.create")

    action = "created"
    treatment = None
    if linked is not None:
        invoices = _invoices_for(linked)
        if _is_settled(invoices):
            linked.odontogram_id = None  # paid work stays as it was; new work gets its own record
        else:
            treatment = linked
            action = "updated"
            treatment.procedure = procedure
            treatment.description = description
            treatment.fee = fee
            treatment.status = "completed"
            for invoice in invoices:
                _reprice(invoice, fee)

    if treatment is None:
        doctor_id = user.id if user.role in ("head_doctor", "doctor") else None
        treatment = Treatment(
            clinic_id=record.clinic_id,
            patient_id=record.patient_id,
            doctor_id=doctor_id,
            created_by=user.id,
            odontogram_id=record.id,
            tooth_number=tooth_number,
            status="completed",
            fee=fee,
            procedure=procedure,
            description=description,
            date=date.today(),
        )
        db.session.add(treatment)
        db.session.flush()
        invoices = []

    invoice_id = invoices[0].id if invoices else None
    if not invoices and want_invoice and fee > 0:
        invoice = Invoice(
            clinic_id=record.clinic_id,
            patient_id=record.patient_id,
            treatment_id=treatment.id,
            amount=fee,
            discount=Decimal("0.00"),
            paid_amount=Decimal("0.00"),
            balance=fee,
            status="unpaid",
            created_by=user.id,
        )
        db.session.add(invoice)
        db.session.flush()
        invoice_id = invoice.id

    return {
        "action": action,
        "treatment_id": treatment.id,
        "invoice_id": invoice_id,
        "fee": format(fee, ".2f"),
    }
