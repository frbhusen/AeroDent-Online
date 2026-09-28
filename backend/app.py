import os
from flask import Flask, jsonify
from sqlalchemy.exc import DataError
from werkzeug.routing import IntegerConverter
from werkzeug.security import safe_join

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
from backend.routes.trial import trial_blueprint
from backend.services.static_assets import StaticAssets


class DatabaseIdConverter(IntegerConverter):
    """<int:...> URL segments limited to PostgreSQL's integer range, so an oversized ID is a
    plain 404 instead of reaching the database and failing there."""

    def __init__(self, map, *args, **kwargs):
        kwargs.setdefault("min", 0)
        kwargs.setdefault("max", 2_147_483_647)
        super().__init__(map, *args, **kwargs)


WEB_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "web"))


def create_app() -> Flask:
    # static_folder=None: every frontend file goes through serve_frontend so caching headers
    # are applied consistently (see backend/services/static_assets.py and docs/CACHING.md).
    app = Flask(__name__, static_folder=None)
    app.url_map.converters["int"] = DatabaseIdConverter
    app.config.from_object(Config)
    assets = StaticAssets(WEB_DIR)
    app.extensions["aerodent_assets"] = assets

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
    app.register_blueprint(trial_blueprint)

    from backend.cli import admin_cli, xrays_cli

    app.cli.add_command(xrays_cli)
    app.cli.add_command(admin_cli)

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
        response.headers["X-Frame-Options"] = "DENY"
        # The legacy XSS auditor is removed from modern browsers and could itself be abused;
        # the Content-Security-Policy below is the real protection.
        response.headers["X-XSS-Protection"] = "0"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=(), payment=(), usb=()"
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
        # No inline scripts or inline event handlers exist in the frontend, so scripts are
        # restricted to our own origin. Inline style attributes are still used by templates.
        # Responses that set a stricter policy of their own (e.g. sandboxed X-ray files) keep it.
        response.headers.setdefault("Content-Security-Policy", (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self'; "
            "worker-src 'self'; manifest-src 'self'; object-src 'none'; base-uri 'self'; "
            "form-action 'self'; frame-ancestors 'none'"
        ))
        if app.config.get("SESSION_COOKIE_SECURE"):
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        if req.path.startswith("/api/"):
            # API responses carry clinic/patient data and depend on the session cookie:
            # never store them in any browser, proxy, or shared cache.
            response.headers["Cache-Control"] = "no-store, private"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
            response.vary.add("Cookie")
        return response

    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    def serve_frontend(path):
        if path.startswith("api/") or path == "api":
            return {"error": "Endpoint not found."}, 404
        if path == "":
            # The site root is the public marketing landing page (web/landing page/).
            return assets.serve_landing_home()
        if path in ("login", "index.html"):
            # The application shell (login screen + dashboard SPA) lives at /login.
            return assets.serve_index()
        if path == "trial.html":
            # Only reachable through the gated /request-trial route.
            return assets.serve_index()
        if path == "sw.js":
            return assets.serve_service_worker()
        target_path = safe_join(WEB_DIR, path)
        if target_path and os.path.isfile(target_path):
            return assets.serve_file(path)
        return assets.serve_index()

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
        return assets.serve_index()

    @app.errorhandler(405)
    def method_not_allowed(e):
        return jsonify({"error": "HTTP method not allowed for this endpoint."}), 405

    @app.errorhandler(413)
    def payload_too_large(e):
        return jsonify({"error": "Request payload exceeds the maximum allowed size."}), 413

    @app.errorhandler(429)
    def rate_limited(e):
        return jsonify({"error": "Too many requests. Please slow down."}), 429

    @app.errorhandler(DataError)
    def invalid_database_value(e):
        # A value the database cannot represent (e.g. an out-of-range number in a query
        # parameter) is a client input error, not a server fault.
        db.session.rollback()
        return jsonify({"error": "Invalid input value."}), 400

    @app.errorhandler(500)
    def internal_error(e):
        db.session.rollback()
        return jsonify({"error": "An internal server error occurred."}), 500

    return app


app = create_app()


if __name__ == "__main__":
    # The interactive debugger allows arbitrary code execution; never enable it outside
    # local development. Production must run behind a WSGI server (see README).
    app.run(debug=Config.ENVIRONMENT == "development")