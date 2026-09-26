import os
import secrets
from datetime import timedelta

from dotenv import load_dotenv


load_dotenv()


class Config:
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL")

    if not SQLALCHEMY_DATABASE_URI:
        raise RuntimeError(
            "DATABASE_URL is not configured. "
            "Create a .env file in the project root."
        )

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    ENVIRONMENT = os.getenv("AERODENT_ENV", "development").lower()
    SECRET_KEY = os.getenv("SECRET_KEY")

    if not SECRET_KEY:
        if ENVIRONMENT == "production":
            raise RuntimeError(
                "SECRET_KEY is required when AERODENT_ENV=production."
            )
        SECRET_KEY = secrets.token_hex(32)

    if ENVIRONMENT == "production" and len(SECRET_KEY) < 32:
        raise RuntimeError("SECRET_KEY must be at least 32 characters in production.")

    # Session cookie: HTTP-only, SameSite=Strict (the app is a same-origin SPA, so the cookie
    # is never needed on cross-site requests), Secure + "__Host-" prefix in production (the
    # prefix forces Secure, Path=/ and no Domain attribute, so subdomains cannot overwrite it).
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SECURE = ENVIRONMENT == "production"
    SESSION_COOKIE_SAMESITE = "Strict"
    SESSION_COOKIE_PATH = "/"
    SESSION_COOKIE_NAME = "__Host-aerodent_session" if ENVIRONMENT == "production" else "aerodent_session"

    # Server-side session validity (enforced against the user_sessions table on every request):
    # idle timeout since the last request, and an absolute cap from sign-in.
    SESSION_IDLE_TIMEOUT = timedelta(minutes=int(os.getenv("AERODENT_SESSION_IDLE_MINUTES", "120")))
    SESSION_ABSOLUTE_TIMEOUT = timedelta(hours=int(os.getenv("AERODENT_SESSION_MAX_HOURS", "12")))
    PERMANENT_SESSION_LIFETIME = SESSION_ABSOLUTE_TIMEOUT
    SESSION_REFRESH_EACH_REQUEST = True

    # Public self-service clinic registration. Off by default: prospective clinics use the
    # trial-request page, and clinics are provisioned by the platform Super Admin.
    ALLOW_SELF_REGISTRATION = os.getenv("AERODENT_ALLOW_SELF_REGISTRATION", "false").lower() == "true"

    # Only trust the X-Forwarded-For header when actually deployed behind a reverse proxy
    # that itself strips/overwrites any client-supplied X-Forwarded-For. Left False, the
    # rate limiter and audit log always use the direct socket peer address, which a client
    # cannot spoof.
    TRUST_PROXY_HEADERS = os.getenv("TRUST_PROXY_HEADERS", "False").lower() == "true"

    AERODENT_STORAGE_PATH = os.getenv(
        "AERODENT_STORAGE_PATH",
        os.path.join(os.path.dirname(os.path.dirname(__file__)), "storage"),
    )
    # X-ray uploads are stored losslessly in PostgreSQL; uncompressed 16-bit panoramics can be
    # large, so the limit is configurable. The whole request may be slightly larger (form fields).
    XRAY_MAX_UPLOAD_BYTES = int(os.getenv("AERODENT_XRAY_MAX_MB", "25")) * 1024 * 1024
    MAX_CONTENT_LENGTH = XRAY_MAX_UPLOAD_BYTES + 1024 * 1024  # bounds memory use per request