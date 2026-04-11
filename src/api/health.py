import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.dependencies import get_db

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Observability"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": settings.service_name,
        "version": settings.service_version,
    }


@router.get("/ready")
async def ready(db: AsyncSession = Depends(get_db)) -> dict[str, str]:
    try:
        await db.execute(text("SELECT 1"))
    except Exception as exc:
        logger.error("Readiness check failed: DB unavailable", extra={"error": str(exc)})
        raise HTTPException(status_code=503, detail={"status": "not_ready", "database": "error"})

    return {"status": "ready", "database": "ok"}
