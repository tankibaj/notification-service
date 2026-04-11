from fastapi import APIRouter

from src.api.health import router as health_router
from src.api.v1.notifications import router as notifications_router

router = APIRouter()

router.include_router(health_router)
router.include_router(notifications_router, prefix="/api/v1")
