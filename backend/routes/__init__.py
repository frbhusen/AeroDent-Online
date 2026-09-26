from backend.routes.appointments import appointments_blueprint
from backend.routes.prescriptions import prescriptions_blueprint
from backend.routes.xrays import xrays_blueprint
from backend.routes.invoices import invoices_blueprint
from backend.routes.odontogram import odontogram_blueprint
from backend.routes.patients import patients_blueprint
from backend.routes.treatments import treatments_blueprint
from backend.routes.treatment_plans import treatment_plans_blueprint

__all__ = [
	"odontogram_blueprint",
	"appointments_blueprint",
	"prescriptions_blueprint",
	"xrays_blueprint",
	"invoices_blueprint",
	"patients_blueprint",
	"treatments_blueprint",
	"treatment_plans_blueprint",
]