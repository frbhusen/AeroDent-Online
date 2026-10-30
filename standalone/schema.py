"""Creates and upgrades the local SQLite schema of the standalone edition.

The online edition's Alembic migrations are written for PostgreSQL (named constraints etc.) and do
not run on SQLite, so the desktop edition builds its schema from the models instead:

* a new database gets every table (``create_all``);
* when an update adds tables, they are created the same way;
* when an update adds columns, they are added with ``ALTER TABLE ... ADD COLUMN``. Only additive,
  safe changes are applied automatically (nullable columns, or columns with a default). Anything
  else raises, so a release that needs a real data migration cannot silently start on old data.
"""

from sqlalchemy import inspect, text
from sqlalchemy.schema import CreateColumn

SCHEMA_VERSION = 1  # bump when a release needs a hand-written upgrade step in UPGRADES
UPGRADES = {}  # {from_version: callable(connection)} for changes that are not purely additive


def ensure_schema(db):
    """Brings the database in line with the models. Returns the list of columns it added."""
    import backend.models  # noqa: F401  (registers every table on the metadata)

    db.create_all()
    added = []
    inspector = inspect(db.engine)
    with db.engine.begin() as connection:
        for table in db.metadata.sorted_tables:
            existing = {column["name"] for column in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in existing:
                    continue
                if not column.nullable and column.server_default is None:
                    raise RuntimeError(
                        f"Column {table.name}.{column.name} is NOT NULL without a default; "
                        "this update needs a manual upgrade step in standalone/schema.py."
                    )
                ddl = CreateColumn(column).compile(dialect=db.engine.dialect)
                connection.execute(text(f"ALTER TABLE {table.name} ADD COLUMN {ddl}"))
                added.append(f"{table.name}.{column.name}")
        connection.execute(text("CREATE TABLE IF NOT EXISTS standalone_meta (key TEXT PRIMARY KEY, value TEXT)"))
        row = connection.execute(text("SELECT value FROM standalone_meta WHERE key = 'schema_version'")).fetchone()
        current = int(row[0]) if row else SCHEMA_VERSION
        while current < SCHEMA_VERSION:
            UPGRADES[current](connection)
            current += 1
        connection.execute(
            text("INSERT OR REPLACE INTO standalone_meta (key, value) VALUES ('schema_version', :v)"),
            {"v": str(SCHEMA_VERSION)},
        )
    return added
