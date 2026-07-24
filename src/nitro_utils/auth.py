import logging
import secrets

from fastapi import Request, Response
from fastapi.responses import ORJSONResponse
from itsdangerous import BadSignature, URLSafeTimedSerializer

from nitro_utils.config import settings

logger = logging.getLogger(__name__)

COOKIE_NAME = "nitro_session"
COOKIE_MAX_AGE = 315_360_000

_serializer = URLSafeTimedSerializer(settings.auth_secret_key)


def _auth_enabled() -> bool:
    return bool(settings.auth_password)


def _create_token() -> str:
    return _serializer.dumps({"nonce": secrets.token_hex(8)})


def _validate_token(token: str) -> bool:
    try:
        _serializer.loads(token, max_age=COOKIE_MAX_AGE)
        return True
    except BadSignature:
        return False


_AUTH_EXEMPT_PREFIXES = ("/health",)


async def auth_middleware(request: Request, call_next):  # type: ignore[no-untyped-def]
    if not _auth_enabled():
        return await call_next(request)

    path = request.url.path

    is_exempt = any(path.startswith(prefix) for prefix in _AUTH_EXEMPT_PREFIXES)
    is_api = path.startswith("/api/")

    if not is_api or is_exempt:
        return await call_next(request)

    cookie_token = request.cookies.get(COOKIE_NAME)
    if cookie_token and _validate_token(cookie_token):
        return await call_next(request)

    return ORJSONResponse(
        status_code=401,
        content={"error": {"code": "UNAUTHORIZED", "message": "Not authenticated"}},
    )
