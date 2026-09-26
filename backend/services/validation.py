"""Shared request-input helpers."""

# PostgreSQL INTEGER range; every primary/foreign key in AeroDent is an INTEGER column.
MAX_DB_INT = 2_147_483_647
# Generous upper bound for page numbers so OFFSET arithmetic can never overflow.
MAX_PAGE = 1_000_000


def query_int(raw, maximum=MAX_DB_INT):
    """
    int() for query-string values that also rejects numbers the database cannot hold.

    Raises ValueError (like int()) so existing ``except ValueError`` handling turns an
    out-of-range value into a normal 400 instead of a database error.
    """
    value = int(raw)
    if value < -MAX_DB_INT or value > maximum:
        raise ValueError("Integer out of range.")
    return value


def query_page(raw):
    return query_int(raw, maximum=MAX_PAGE)
