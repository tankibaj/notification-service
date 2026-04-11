import uuid
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.notification import Notification


class NotificationRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create(
        self,
        *,
        tenant_id: uuid.UUID,
        channel: str,
        template_id: str,
        recipient_address: str,
        recipient_name: str | None,
        payload: dict[str, Any],
        idempotency_key: str | None,
    ) -> Notification:
        notification = Notification(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            channel=channel,
            template_id=template_id,
            recipient_address=recipient_address,
            recipient_name=recipient_name,
            payload=payload,
            status="queued",
            retry_count=0,
            idempotency_key=idempotency_key,
        )
        self._db.add(notification)
        try:
            await self._db.commit()
            await self._db.refresh(notification)
            return notification
        except IntegrityError:
            # Race condition: another request inserted the same idempotency key first.
            await self._db.rollback()
            if idempotency_key is not None:
                existing = await self.find_by_idempotency_key(tenant_id, idempotency_key)
                if existing:
                    return existing
            raise
        except DBAPIError as exc:
            await self._db.rollback()
            raise HTTPException(
                status_code=422,
                detail={"code": "VALIDATION_ERROR", "message": "Request data is invalid"},
            ) from exc

    async def get_by_id(
        self, notification_id: uuid.UUID, tenant_id: uuid.UUID
    ) -> Notification | None:
        result = await self._db.execute(
            select(Notification).where(
                Notification.id == notification_id,
                Notification.tenant_id == tenant_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_by_id_internal(
        self, notification_id: uuid.UUID, _any_tenant: bool = False
    ) -> Notification | None:
        """Fetch notification by ID without tenant scoping — for internal processing only."""
        result = await self._db.execute(
            select(Notification).where(Notification.id == notification_id)
        )
        return result.scalar_one_or_none()

    async def find_by_idempotency_key(
        self, tenant_id: uuid.UUID, idempotency_key: str
    ) -> Notification | None:
        result = await self._db.execute(
            select(Notification).where(
                Notification.tenant_id == tenant_id,
                Notification.idempotency_key == idempotency_key,
            )
        )
        return result.scalar_one_or_none()

    async def update_status(
        self,
        notification_id: uuid.UUID,
        status: str,
        retry_count: int | None = None,
        delivered_at: Any = None,
    ) -> None:
        values: dict[str, Any] = {"status": status}
        if retry_count is not None:
            values["retry_count"] = retry_count
        if delivered_at is not None:
            values["delivered_at"] = delivered_at
        await self._db.execute(
            update(Notification).where(Notification.id == notification_id).values(**values)
        )
        await self._db.commit()
