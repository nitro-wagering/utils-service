import logging
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, ORJSONResponse

from nitro_utils.api import api_router
from nitro_utils.auth import auth_middleware
from nitro_utils.config import settings

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info("Utils service starting")
    app.state.http_client = httpx.AsyncClient(
        timeout=httpx.Timeout(settings.service_timeout),
        limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
    )
    yield
    await app.state.http_client.aclose()
    logger.info("Utils service stopped")


app = FastAPI(
    title="Nitro Utils API",
    version="0.1.0",
    default_response_class=ORJSONResponse,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.middleware("http")(auth_middleware)


@app.exception_handler(RequestValidationError)
async def validation_error_response(_request: Request, exc: RequestValidationError) -> Response:
    """422 with the problems but not the rejected input.

    FastAPI echoes each rejected value; a JSON body of NaN or Infinity then cannot be written
    back as JSON and the client got a 500 instead of the 422.
    """
    detail = [
        {key: value for key, value in error.items() if key not in ("input", "ctx")}
        for error in exc.errors()
    ]
    return ORJSONResponse(status_code=422, content={"detail": detail})


@app.middleware("http")
async def request_logging(request: Request, call_next):  # type: ignore[no-untyped-def]
    request_id = request.headers.get("x-request-id", "")
    start = time.monotonic()
    response: Response = await call_next(request)
    duration_ms = (time.monotonic() - start) * 1000
    logger.info(
        "%s %s %d %.1fms rid=%s",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
        request_id,
    )
    if request_id:
        response.headers["x-request-id"] = request_id
    return response


app.include_router(api_router)


@app.get("/", response_class=HTMLResponse)
async def root() -> str:
    """Serve the index/landing page."""
    template_path = Path(__file__).parent / "templates" / "index.html"
    return template_path.read_text(encoding="utf-8")


@app.get("/monitor", response_class=HTMLResponse)
async def monitor() -> str:
    """Serve the race day monitor UI page."""
    template_path = Path(__file__).parent / "templates" / "monitor.html"
    return template_path.read_text(encoding="utf-8")


@app.get("/health")
async def health_check() -> dict:
    return {
        "status": "ok",
        "service": "utils-service",
        "version": "0.1.0",
    }
