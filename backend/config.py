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

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SECURE = ENVIRONMENT == "production"
    SESSION_COOKIE_SAMESITE = "Lax"

    # Sessions expire after 8 hours of inactivity
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)
    SESSION_REFRESH_EACH_REQUEST = True

    AERODENT_STORAGE_PATH = os.getenv(
        "AERODENT_STORAGE_PATH",
        os.path.join(os.path.dirname(os.path.dirname(__file__)), "storage"),
    )
    XRAY_MAX_UPLOAD_BYTES = 15 * 1024 * 1024
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB maximum payload limit to prevent memory exhaustion DoS