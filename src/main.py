import logging
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request, Response
from prometheus_fastapi_instrumentator import Instrumentator  # type: ignore[import-untyped]

from src.config import settings
from src.logging_config import configure_logging

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
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
