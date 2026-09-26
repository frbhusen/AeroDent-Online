import os
from flask import Flask, jsonify, send_from_directory

from backend.config import Config
from backend.extensions import db, migrate
from backend.auth.routes import auth_blueprint
from backend.routes.odontogram import odontogram_blueprint
from backend.routes.patients import patients_blueprint
from backend.routes.treatments import treatments_blueprint
from backend.routes.treatment_plans import treatment_plans_blueprint
from backend.routes.appointments import appointments_blueprint
from backend.routes.prescriptions import prescriptions_blueprint
from backend.routes.xrays import xrays_blueprint
from backend.routes.invoices import invoices_blueprint
from backend.routes.dashboard import dashboard_blueprint
from backend.routes.settings import settings_blueprint
from backend.routes.staff import staff_blueprint
from backend.routes.timeline import timeline_blueprint
from backend.routes.admin import admin_blueprint
from backend.routes.audit_logs import audit_blueprint
from backend.routes.payments import payments_blueprint
from backend.routes.waitlist import waitlist_blueprint
from backend.routes.hr import hr_blueprint
from backend.routes.inventory import inventory_blueprint


WEB_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "web"))


def create_app() -> Flask:
    app = Flask(__name__, static_folder=WEB_DIR, static_url_path="")
    app.config.from_object(Config)

    db.init_app(app)
    migrate.init_app(app, db)
    app.register_blueprint(auth_blueprint)
    app.register_blueprint(odontogram_blueprint)
    app.register_blueprint(patients_blueprint)
    app.register_blueprint(treatments_blueprint)
    app.register_blueprint(treatment_plans_blueprint)
    app.register_blueprint(appointments_blueprint)
    app.register_blueprint(prescriptions_blueprint)
    app.register_blueprint(xrays_blueprint)
    app.register_blueprint(invoices_blueprint)
    app.register_blueprint(dashboard_blueprint)
    app.register_blueprint(settings_blueprint)
    app.register_blueprint(staff_blueprint)
    app.register_blueprint(timeline_blueprint)
    app.register_blueprint(admin_blueprint)
    app.register_blueprint(audit_blueprint)
    app.register_blueprint(payments_blueprint)
    app.register_blueprint(waitlist_blueprint)
    app.register_blueprint(hr_blueprint)
    app.register_blueprint(inventory_blueprint)

    from flask import request as req

    # Global cross-origin CSRF protection for all state-changing API endpoints
    @app.before_request
    def enforce_csrf_protection():
        if req.path.startswith("/api/") and req.method in {"POST", "PUT", "PATCH", "DELETE"}:
            expected_origin = req.host_url.rstrip("/")
            origin = req.headers.get("Origin")
            if origin and origin.rstrip("/") != expected_origin:
                return jsonify({"error": "Cross-origin request rejected."}), 403

            referer = req.headers.get("Referer")
            if not origin and referer and not referer.startswith(f"{expected_origin}/"):
                return jsonify({"error": "Cross-origin request rejected."}), 403

    # Global HTTP Security Headers
    @app.after_request
    def set_security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        return response

    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    def serve_frontend(path):
        if path.startswith("api/") or path == "api":
            return {"error": "Endpoint not found."}, 404
        target_path = os.path.join(WEB_DIR, path)
        if path and os.path.isfile(target_path):
            return send_from_directory(WEB_DIR, path)
        return send_from_directory(WEB_DIR, "index.html")

    # Global JSON error handlers — ensure API errors never return HTML
    @app.errorhandler(400)
    def bad_request(e):
        return jsonify({"error": str(e.description)}), 400

    @app.errorhandler(401)
    def unauthorized(e):
        return jsonify({"error": "Authentication required."}), 401

    @app.errorhandler(403)
    def forbidden(e):
        return jsonify({"error": "You do not have permission to perform this action."}), 403

    @app.errorhandler(404)
    def not_found(e):
        # Only return JSON for API paths; serve the SPA otherwise
        if req.path.startswith("/api/"):
            return jsonify({"error": "The requested endpoint does not exist."}), 404
        return send_from_directory(WEB_DIR, "index.html")

    @app.errorhandler(405)
    def method_not_allowed(e):
        return jsonify({"error": "HTTP method not allowed for this endpoint."}), 405

    @app.errorhandler(413)
    def payload_too_large(e):
        return jsonify({"error": "Request payload exceeds maximum allowed size (16MB)."}), 413

    @app.errorhandler(429)
    def rate_limited(e):
        return jsonify({"error": "Too many requests. Please slow down."}), 429

    @app.errorhandler(500)
    def internal_error(e):
        db.session.rollback()
        return jsonify({"error": "An internal server error occurred."}), 500

    return app


app = create_app()


if __name__ == "__main__":
    app.run(debug=True)