from flask import Blueprint, g, jsonify, request
from sqlalchemy import func

from backend.auth.routes import login_required
from backend.extensions import db
from backend.models.audit_log import AuditLog


audit_blueprint = Blueprint("audit_logs", __name__, url_prefix="/api/audit-logs")


@audit_blueprint.get("")
@login_required
def list_audit_logs():
    user = g.current_user
    # Only super_admin and head_doctor can inspect audit logs
    if user.role not in {"super_admin", "head_doctor"}:
        return jsonify({"error": "Forbidden. Audit logs are restricted to Head Doctors and Super Admins."}), 403

    query = db.select(AuditLog)

    if user.role != "super_admin":
        query = query.where(AuditLog.clinic_id == user.clinic_id)
    else:
        clinic_filter = request.args.get("clinic_id", type=int)
        if clinic_filter:
            query = query.where(AuditLog.clinic_id == clinic_filter)

    action_filter = request.args.get("action")
    if action_filter:
        query = query.where(AuditLog.action == action_filter)

    resource_filter = request.args.get("resource_type")
    if resource_filter:
        query = query.where(AuditLog.resource_type == resource_filter)

    limit = min(request.args.get("limit", default=50, type=int), 200)
    offset = max(request.args.get("offset", default=0, type=int), 0)

    total = db.session.scalar(db.select(func.count()).select_from(query.subquery()))
    logs = db.session.scalars(
        query.order_by(AuditLog.created_at.desc()).limit(limit).offset(offset)
    ).all()

    items = []
    for l in logs:
        items.append({
            "id": l.id,
            "clinic_id": l.clinic_id,
            "user_id": l.user_id,
            "user_name": l.user_name or "System",
            "user_role": l.user_role or "-",
            "action": l.action,
            "resource_type": l.resource_type,
            "resource_id": l.resource_id,
            "details": l.details,
            "ip_address": l.ip_address,
            "created_at": l.created_at.isoformat() if l.created_at else None,
        })

    return jsonify({"data": items, "total": total, "limit": limit, "offset": offset})
