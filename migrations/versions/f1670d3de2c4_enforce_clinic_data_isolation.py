"""Enforce clinic data isolation

Revision ID: f1670d3de2c4
Revises: 58ebb0c75e66
Create Date: 2026-09-20 16:07:39.489748

"""

from alembic import op


revision = "f1670d3de2c4"
down_revision = "58ebb0c75e66"
branch_labels = None
depends_on = None


def upgrade():
    # ---------------------------------------------------------
    # 1. Create parent-side unique constraints FIRST.
    # These are required by the composite foreign keys below.
    # ---------------------------------------------------------

    op.create_unique_constraint(
        "uq_user_clinic_id",
        "users",
        ["clinic_id", "id"],
    )

    op.create_unique_constraint(
        "uq_patient_clinic_id",
        "patients",
        ["clinic_id", "id"],
    )

    op.create_unique_constraint(
        "uq_treatment_clinic_id",
        "treatments",
        ["clinic_id", "id"],
    )

    # ---------------------------------------------------------
    # 2. Create unique constraints for child tables.
    # These aren't required by the foreign keys below, but
    # keep (clinic_id, id) uniquely identifiable everywhere.
    # ---------------------------------------------------------

    op.create_unique_constraint(
        "uq_appointment_clinic_id",
        "appointments",
        ["clinic_id", "id"],
    )

    op.create_unique_constraint(
        "uq_invoice_clinic_id",
        "invoices",
        ["clinic_id", "id"],
    )

    op.create_unique_constraint(
        "uq_odontogram_clinic_id",
        "odontograms",
        ["clinic_id", "id"],
    )

    op.create_unique_constraint(
        "uq_prescription_clinic_id",
        "prescriptions",
        ["clinic_id", "id"],
    )

    op.create_unique_constraint(
        "uq_treatment_plan_clinic_id",
        "treatment_plans",
        ["clinic_id", "id"],
    )

    op.create_unique_constraint(
        "uq_xray_clinic_id",
        "x_rays",
        ["clinic_id", "id"],
    )

    # ---------------------------------------------------------
    # 3. Patient -> User
    # ---------------------------------------------------------

    op.create_foreign_key(
        "fk_patient_created_by_clinic",
        "patients",
        "users",
        ["clinic_id", "created_by"],
        ["clinic_id", "id"],
        ondelete="RESTRICT",
    )

    # ---------------------------------------------------------
    # 4. Odontogram -> Patient / User
    # ---------------------------------------------------------

    op.create_foreign_key(
        "fk_odontogram_patient_clinic",
        "odontograms",
        "patients",
        ["clinic_id", "patient_id"],
        ["clinic_id", "id"],
        ondelete="CASCADE",
    )

    op.create_foreign_key(
        "fk_odontogram_created_by_clinic",
        "odontograms",
        "users",
        ["clinic_id", "created_by"],
        ["clinic_id", "id"],
        ondelete="RESTRICT",
    )

    # ---------------------------------------------------------
    # 5. Treatment -> Patient / User
    # ---------------------------------------------------------

    op.create_foreign_key(
        "fk_treatment_patient_clinic",
        "treatments",
        "patients",
        ["clinic_id", "patient_id"],
        ["clinic_id", "id"],
        ondelete="CASCADE",
    )

    op.create_foreign_key(
        "fk_treatment_doctor_clinic",
        "treatments",
        "users",
        ["clinic_id", "doctor_id"],
        ["clinic_id", "id"],
        ondelete="RESTRICT",
    )

    op.create_foreign_key(
        "fk_treatment_created_by_clinic",
        "treatments",
        "users",
        ["clinic_id", "created_by"],
        ["clinic_id", "id"],
        ondelete="RESTRICT",
    )

    # ---------------------------------------------------------
    # 6. Treatment plan -> Patient / User
    # ---------------------------------------------------------

    op.create_foreign_key(
        "fk_treatment_plan_patient_clinic",
        "treatment_plans",
        "patients",
        ["clinic_id", "patient_id"],
        ["clinic_id", "id"],
        ondelete="CASCADE",
    )

    op.create_foreign_key(
        "fk_treatment_plan_doctor_clinic",
        "treatment_plans",
        "users",
        ["clinic_id", "doctor_id"],
        ["clinic_id", "id"],
        ondelete="RESTRICT",
    )

    op.create_foreign_key(
        "fk_treatment_plan_created_by_clinic",
        "treatment_plans",
        "users",
        ["clinic_id", "created_by"],
        ["clinic_id", "id"],
        ondelete="RESTRICT",
    )

    # ---------------------------------------------------------
    # 7. Appointment -> Patient / User
    # ---------------------------------------------------------

    op.create_foreign_key(
        "fk_appointment_patient_clinic",
        "appointments",
        "patients",
        ["clinic_id", "patient_id"],
        ["clinic_id", "id"],
        ondelete="CASCADE",
    )

    op.create_foreign_key(
        "fk_appointment_doctor_clinic",
        "appointments",
        "users",
        ["clinic_id", "doctor_id"],
        ["clinic_id", "id"],
        ondelete="RESTRICT",
    )

    op.create_foreign_key(
        "fk_appointment_created_by_clinic",
        "appointments",
        "users",
        ["clinic_id", "created_by"],
        ["clinic_id", "id"],
        ondelete="RESTRICT",
    )

    # ---------------------------------------------------------
    # 8. Prescription -> Patient / User
    # ---------------------------------------------------------

    op.create_foreign_key(
        "fk_prescription_patient_clinic",
        "prescriptions",
        "patients",
        ["clinic_id", "patient_id"],
        ["clinic_id", "id"],
        ondelete="CASCADE",
    )

    op.create_foreign_key(
        "fk_prescription_doctor_clinic",
        "prescriptions",
        "users",
        ["clinic_id", "doctor_id"],
        ["clinic_id", "id"],
        ondelete="RESTRICT",
    )

    op.create_foreign_key(
        "fk_prescription_created_by_clinic",
        "prescriptions",
        "users",
        ["clinic_id", "created_by"],
        ["clinic_id", "id"],
        ondelete="RESTRICT",
    )

    # ---------------------------------------------------------
    # 9. X-Ray -> Patient / User
    # ---------------------------------------------------------

    op.create_foreign_key(
        "fk_xray_patient_clinic",
        "x_rays",
        "patients",
        ["clinic_id", "patient_id"],
        ["clinic_id", "id"],
        ondelete="CASCADE",
    )

    op.create_foreign_key(
        "fk_xray_uploaded_by_clinic",
        "x_rays",
        "users",
        ["clinic_id", "uploaded_by"],
        ["clinic_id", "id"],
        ondelete="RESTRICT",
    )

    # ---------------------------------------------------------
    # 10. Invoice -> Patient / Treatment / User
    # ---------------------------------------------------------

    op.create_foreign_key(
        "fk_invoice_patient_clinic",
        "invoices",
        "patients",
        ["clinic_id", "patient_id"],
        ["clinic_id", "id"],
        ondelete="CASCADE",
    )

    op.create_foreign_key(
        "fk_invoice_treatment_clinic",
        "invoices",
        "treatments",
        ["clinic_id", "treatment_id"],
        ["clinic_id", "id"],
        ondelete="RESTRICT",
    )

    op.create_foreign_key(
        "fk_invoice_created_by_clinic",
        "invoices",
        "users",
        ["clinic_id", "created_by"],
        ["clinic_id", "id"],
        ondelete="RESTRICT",
    )


def downgrade():
    # ---------------------------------------------------------
    # Drop foreign keys FIRST.
    # ---------------------------------------------------------

    op.drop_constraint(
        "fk_invoice_created_by_clinic",
        "invoices",
        type_="foreignkey",
    )

    op.drop_constraint(
        "fk_invoice_treatment_clinic",
        "invoices",
        type_="foreignkey",
    )

    op.drop_constraint(
        "fk_invoice_patient_clinic",
        "invoices",
        type_="foreignkey",
    )

    op.drop_constraint(
        "fk_xray_uploaded_by_clinic",
        "x_rays",
        type_="foreignkey",
    )

    op.drop_constraint(
        "fk_xray_patient_clinic",
        "x_rays",
        type_="foreignkey",
    )

    op.drop_constraint(
        "fk_prescription_created_by_clinic",
        "prescriptions",
        type_="foreignkey",
    )

    op.drop_constraint(
        "fk_prescription_doctor_clinic",
        "prescriptions",
        type_="foreignkey",
    )

    op.drop_constraint(
        "fk_prescription_patient_clinic",
        "prescriptions",
        type_="foreignkey",
    )

    op.drop_constraint(
        "fk_appointment_created_by_clinic",
        "appointments",
        type_="foreignkey",
    )

    op.drop_constraint(
        "fk_appointment_doctor_clinic",
        "appointments",
        type_="foreignkey",
    )

    op.drop_constraint(
        "fk_appointment_patient_clinic",
        "appointments",
        type_="foreignkey",
    )

    op.drop_constraint(
        "fk_treatment_plan_created_by_clinic",
        "treatment_plans",
        type_="foreignkey",
    )

    op.drop_constraint(
        "fk_treatment_plan_doctor_clinic",
        "treatment_plans",
        type_="foreignkey",
    )

    op.drop_constraint(
        "fk_treatment_plan_patient_clinic",
        "treatment_plans",
        type_="foreignkey",
    )

    op.drop_constraint(
        "fk_treatment_created_by_clinic",
        "treatments",
        type_="foreignkey",
    )

    op.drop_constraint(
        "fk_treatment_doctor_clinic",
        "treatments",
        type_="foreignkey",
    )

    op.drop_constraint(
        "fk_treatment_patient_clinic",
        "treatments",
        type_="foreignkey",
    )

    op.drop_constraint(
        "fk_odontogram_created_by_clinic",
        "odontograms",
        type_="foreignkey",
    )

    op.drop_constraint(
        "fk_odontogram_patient_clinic",
        "odontograms",
        type_="foreignkey",
    )

    op.drop_constraint(
        "fk_patient_created_by_clinic",
        "patients",
        type_="foreignkey",
    )

    # ---------------------------------------------------------
    # Drop unique constraints AFTER foreign keys.
    # ---------------------------------------------------------

    op.drop_constraint(
        "uq_xray_clinic_id",
        "x_rays",
        type_="unique",
    )

    op.drop_constraint(
        "uq_treatment_plan_clinic_id",
        "treatment_plans",
        type_="unique",
    )

    op.drop_constraint(
        "uq_prescription_clinic_id",
        "prescriptions",
        type_="unique",
    )

    op.drop_constraint(
        "uq_odontogram_clinic_id",
        "odontograms",
        type_="unique",
    )

    op.drop_constraint(
        "uq_invoice_clinic_id",
        "invoices",
        type_="unique",
    )

    op.drop_constraint(
        "uq_appointment_clinic_id",
        "appointments",
        type_="unique",
    )

    op.drop_constraint(
        "uq_treatment_clinic_id",
        "treatments",
        type_="unique",
    )

    op.drop_constraint(
        "uq_patient_clinic_id",
        "patients",
        type_="unique",
    )

    op.drop_constraint(
        "uq_user_clinic_id",
        "users",
        type_="unique",
    )