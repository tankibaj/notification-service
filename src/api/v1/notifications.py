import asyncio
import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.dependencies import get_db, get_tenant_id
from src.repositories.notification_repository import NotificationRepository
from src.schemas.notification import NotificationReceipt, SendNotificationRequest
from src.services.notification_service import NotificationService
from src.services.smtp_client import SMTPClient
from src.services.template_engine import TemplateEngine

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Notifications"])

_smtp_client = SMTPClient(
    host=settings.smtp_host,
    port=settings.smtp_port,
    sender=settings.smtp_sender,
)
_template_engine = TemplateEngine()


def get_notification_service(db: AsyncSession = Depends(get_db)) -> NotificationService:
    return NotificationService(
        db=db,
        smtp_client=_smtp_client,
        template_engine=_template_engine,
    )


@router.post("/notifications", status_code=202, response_model=NotificationReceipt)
async def send_notification(
    request: SendNotificationRequest,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    service: NotificationService = Depends(get_notification_service),
) -> NotificationReceipt:
    # Normalize idempotency key: empty string is treated as no key
    normalized_key: str | None = idempotency_key if idempotency_key else None

    if normalized_key and len(normalized_key) > 64:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "VALIDATION_ERROR",
                "message": "Idempotency-Key must be 64 characters or fewer",
            },
        )

    notification = await service.create_notification(
        request=request,
        tenant_id=tenant_id,
        idempotency_key=normalized_key,
    )

    notification = await service.create_notification(
        request=request,
        tenant_id=tenant_id,
        idempotency_key=idempotency_key,
    )

    # Fire-and-forget delivery
    asyncio.create_task(service.process_notification(notification.id))

    return NotificationReceipt.model_validate(notification)


@router.get("/notifications/{notification_id}", response_model=NotificationReceipt)
async def get_notification(
    notification_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
) -> NotificationReceipt:
    repo = NotificationRepository(db)
    notification = await repo.get_by_id(notification_id, tenant_id)

    if notification is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "Notification not found"},
        )

    return NotificationReceipt.model_validate(notification)
