"""The suite only ever points the app at a disposable, local test database.

The app engine reads NITRO_DATABASE_URL. conftest assigns it from the test URL and runs this
guard first, so an exported production DSN can neither leak into the app engine nor be the
target of the fixtures' DDL: the host must be loopback and the database name a test database.
Port, user and password are free. CI's service container is named ``test``.
"""

from __future__ import annotations

from sqlalchemy.engine import make_url

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


def is_disposable(url: str) -> bool:
    parsed = make_url(url)
    database = parsed.database or ""
    return parsed.host in LOOPBACK_HOSTS and (
        database in {"test", "nitro_test"} or database.endswith("_test")
    )


def require_disposable(url: str, source: str) -> str:
    """``url`` unchanged; raises ``ValueError`` when it is not a disposable local database."""
    if not is_disposable(url):
        raise ValueError(
            f"{source} must name a loopback host and a database called test, nitro_test or "
            f"*_test; refusing to run the suite against {make_url(url).render_as_string()}"
        )
    return url
