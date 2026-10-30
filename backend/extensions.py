import os

from dotenv import load_dotenv
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate


load_dotenv()

db = SQLAlchemy()
migrate = Migrate()

# The standalone (desktop) edition stores everything in a local SQLite file. SQLite has no real
# timezone-aware columns, so two things are adjusted there and ONLY there; PostgreSQL is untouched:
#   * DateTime columns always come back timezone-aware (UTC), like they do on PostgreSQL;
#   * foreign keys are enforced (SQLite ignores them unless asked).
if (os.getenv("DATABASE_URL") or "").startswith("sqlite"):
    from datetime import timezone

    from sqlalchemy import DateTime, event
    from sqlalchemy.engine import Engine
    from sqlalchemy.types import TypeDecorator

    class UTCDateTime(TypeDecorator):
        impl = DateTime
        cache_ok = True

        def __init__(self, timezone=True, **kwargs):
            super().__init__(timezone=timezone, **kwargs)

        def process_bind_param(self, value, dialect):
            if value is not None and value.tzinfo is not None:
                value = value.astimezone(timezone.utc).replace(tzinfo=None)
            return value

        def process_result_value(self, value, dialect):
            if value is not None and value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)
            return value

    db.DateTime = UTCDateTime

    @event.listens_for(Engine, "connect")
    def _sqlite_foreign_keys(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
