"""The suite only ever points the app at a disposable, local test database.

The app engine reads NITRO_DATABASE_URL. conftest assigns it from the test URL and runs this
guard first, so an exported production DSN can neither leak into the app engine nor be the
target of the fixtures' DDL. The guard checks the host and database the driver will actually
connect to (SQLAlchemy's ``create_connect_args``), not just the URL's authority, because libpq
query parameters override both. The host must be loopback and the database name a test
database. Port, user and password are free. CI's service container is named ``test``.

Same logic as ingestion-worker's tests/isolated_db.py (ingestion #289); keep the two in step.
"""

from __future__ import annotations

from sqlalchemy.engine import make_url

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
CONNECTION_OVERRIDES = frozenset({"host", "hostaddr", "service", "dbname"})


def is_disposable(url: str) -> bool:
    parsed = make_url(url)
    if CONNECTION_OVERRIDES & set(parsed.query):
        return False
    connect_args = parsed.get_dialect()().create_connect_args(parsed)[1]
    database = connect_args.get("dbname") or ""
    return (
        connect_args.get("host") in LOOPBACK_HOSTS
        and "hostaddr" not in connect_args
        and "service" not in connect_args
        and (database in {"test", "nitro_test"} or database.endswith("_test"))
    )


def require_disposable(url: str, source: str) -> str:
    """``url`` unchanged; raises ``ValueError`` (not an assert) when not disposable."""
    if not is_disposable(url):
        raise ValueError(
            f"{source} must name a loopback host and a database called test, nitro_test or "
            f"*_test; refusing to run the suite against {make_url(url).render_as_string()}"
        )
    return url
