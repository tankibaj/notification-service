import logging
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.config import settings
from src.logging_config import configure_logging

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    configure_logging()
    logger.info("notification-service starting up", extra={"version": settings.service_version})
    yield
    logger.info("notification-service shutting down")


def create_app() -> FastAPI:
    configure_logging()

    app = FastAPI(
        title="Notification Service",
        version=settings.service_version,
        lifespan=lifespan,
    )

    # --- Exception handlers: convert to ErrorResponse schema ---

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        detail = exc.detail
        if isinstance(detail, dict) and "code" in detail and "message" in detail:
            # Already in ErrorResponse format
            body = detail
        elif isinstance(detail, str):
            body = {"code": str(exc.status_code), "message": detail}
        else:
            body = {"code": str(exc.status_code), "message": str(detail)}
        return JSONResponse(status_code=exc.status_code, content=body)

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        errors = exc.errors()
        message = "; ".join(f"{'.'.join(str(loc) for loc in e['loc'])}: {e['msg']}" for e in errors)
        return JSONResponse(
            status_code=422,
            content={"code": "VALIDATION_ERROR", "message": message},
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.error(
            "Unhandled exception",
            extra={"path": request.url.path, "error_type": type(exc).__name__},
            exc_info=True,
        )
        return JSONResponse(
            status_code=500,
            content={"code": "INTERNAL_ERROR", "message": "Internal server error"},
        )

    # X-Request-ID propagation middleware
    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next: Any) -> Response:
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        response: Response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    # Register routers
    from src.api.router import router as api_router

    app.include_router(api_router)

    # Prometheus metrics
    Instrumentator().instrument(app).expose(app, endpoint="/metrics")

    return app


app = create_app()

