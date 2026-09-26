from functools import wraps

from flask import g, jsonify


PATIENT_ADMINISTRATIVE_FIELDS = frozenset(
    {
        "name",
        "phone",
        "location",
        "work_study",
        "dob",
        "gender",
    }
)

PATIENT_CLINICAL_FIELDS = frozenset(
    {
        "allergies",
        "medical_flags",
        "notes",
    }
)

PATIENT_IMMUTABLE_FIELDS = frozenset(
    {
        "id",
        "clinic_id",
        "created_by",
        "created_at",
        "updated_at",
    }
)


ROLE_PERMISSIONS = {
    "super_admin": frozenset(
        {
            "admin.read",
            "admin.clinics.read",
            "admin.clinics.create",
            "admin.clinics.update",
            "admin.clinics.delete",
            "admin.users.read",
            "admin.users.create",
            "admin.users.update",
            "admin.users.delete",
            "admin.subscriptions.manage",
        }
    ),
    "head_doctor": frozenset(
        {
            "dashboard.read",
            "patients.read",
            "patients.create",
            "patients.update",
            "patients.delete",
            "odontogram.read",
            "odontogram.update",
            "treatments.read",
            "treatments.create",
            "treatments.update",
            "treatments.delete",
            "treatment_plans.read",
            "treatment_plans.create",
            "treatment_plans.update",
            "treatment_plans.delete",
            "appointments.read",
            "appointments.create",
            "appointments.update",
            "appointments.delete",
            "prescriptions.read",
            "prescriptions.create",
            "prescriptions.update",
            "prescriptions.delete",
            "xrays.read",
            "xrays.create",
            "xrays.update",
            "xrays.delete",
            "invoices.read",
            "invoices.create",
            "invoices.update",
            "invoices.delete",
            "clinic_settings.read",
            "clinic_settings.update",
            "staff.read",
            "staff.create",
            "staff.update",
            "staff.deactivate",
            "staff.delete",
        }
    ),
    "doctor": frozenset(
        {
            "dashboard.read",
            "patients.read",
            "patients.create",
            "patients.update",
            "patients.delete",
            "odontogram.read",
            "odontogram.update",
            "treatments.read",
            "treatments.create",
            "treatments.update",
            "treatments.delete",
            "treatment_plans.read",
            "treatment_plans.create",
            "treatment_plans.update",
            "treatment_plans.delete",
            "appointments.read",
            "appointments.create",
            "appointments.update",
            "appointments.delete",
            "prescriptions.read",
            "prescriptions.create",
            "prescriptions.update",
            "prescriptions.delete",
            "xrays.read",
            "xrays.create",
            "xrays.update",
            "xrays.delete",
            "invoices.read",
            "invoices.create",
            "invoices.update",
            "clinic_settings.read",
        }
    ),
    "secretary": frozenset(
        {
            "dashboard.read",
            "patients.read",
            "patients.create",
            "patients.update",
            "odontogram.read",
            "treatments.read",
            "treatment_plans.read",
            "appointments.read",
            "appointments.create",
            "appointments.update",
            "appointments.delete",
            "prescriptions.read",
            "xrays.read",
            "invoices.read",
            "invoices.create",
            "invoices.update",
        }
    ),
}


def user_has_permission(user, permission):
    if user is None or not isinstance(permission, str):
        return False

    return permission in ROLE_PERMISSIONS.get(user.role, frozenset())


def require_permission(permission):
    def decorator(view):
        @wraps(view)
        def wrapped_view(*args, **kwargs):
            user = getattr(g, "current_user", None)
            if user is None:
                return jsonify({"error": "Authentication required."}), 401

            if not user_has_permission(user, permission):
                return jsonify(
                    {"error": "You do not have permission to perform this action."}
                ), 403

            return view(*args, **kwargs)

        return wrapped_view

    return decorator


def resource_belongs_to_user_clinic(user, resource):
    return (
        user is not None
        and resource is not None
        and user.clinic_id is not None
        and resource.clinic_id == user.clinic_id
    )


def authorize_resource(user, permission, resource):
    return user_has_permission(user, permission) and resource_belongs_to_user_clinic(
        user, resource
    )


def validate_patient_update(user, incoming_data):
    if not user_has_permission(user, "patients.update"):
        raise PermissionError("User cannot update patients.")

    fields = set(incoming_data)
    if fields & PATIENT_IMMUTABLE_FIELDS:
        raise PermissionError("Patient ownership fields cannot be changed.")

    if user.role == "secretary" and fields & PATIENT_CLINICAL_FIELDS:
        raise PermissionError("Secretaries cannot update clinical patient fields.")

    return True