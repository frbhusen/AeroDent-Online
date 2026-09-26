import json

from flask import current_app, request

from backend.extensions import db
from backend.models.audit_log import AuditLog


def get_client_ip():
    """
    Returns the direct socket peer address unless TRUST_PROXY_HEADERS is enabled, in which
    case the app is assumed to sit behind a reverse proxy that strips/overwrites any
    client-supplied X-Forwarded-For, so the header's first entry can be trusted instead.
    """
    trust_proxy = False
    try:
        trust_proxy = bool(current_app.config.get("TRUST_PROXY_HEADERS"))
    except RuntimeError:
        pass

    if trust_proxy:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()

    return request.remote_addr


def log_activity(
    action,
    resource_type,
    resource_id=None,
    details=None,
    clinic_id=None,
    user_id=None,
    user_name=None,
    user_role=None,
    ip_address=None,
):
    """
    Records an immutable audit log entry.
    Automatically infers clinic_id, user_id, and ip_address from Flask context if available.
    """
    try:
        from flask import g

        if clinic_id is None:
            clinic = getattr(g, "current_clinic", None)
            if clinic:
                clinic_id = clinic.id
            elif getattr(g, "current_user", None) and g.current_user.clinic_id:
                clinic_id = g.current_user.clinic_id

        if user_id is None and getattr(g, "current_user", None):
            user_id = g.current_user.id
            user_name = user_name or g.current_user.name
            user_role = user_role or g.current_user.role

        if ip_address is None:
            try:
                ip_address = get_client_ip()
            except Exception:
                ip_address = None

        if isinstance(details, (dict, list)):
            details_str = json.dumps(details)
        else:
            details_str = str(details) if details is not None else None

        entry = AuditLog(
            clinic_id=clinic_id,
            user_id=user_id,
            user_name=user_name,
            user_role=user_role,
            action=action,
            resource_type=resource_type,
            resource_id=str(resource_id) if resource_id is not None else None,
            details=details_str,
            ip_address=ip_address,
        )
        db.session.add(entry)
        db.session.flush()
        return entry
    except Exception as err:
        # Never fail the parent transaction if audit logging encounters an issue
        print(f"Warning: Failed to log audit activity: {err}")
        return None
