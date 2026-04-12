import asyncio
import logging
import uuid
from datetime import UTC, datetime

from prometheus_client import Counter, Histogram
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.notification import Notification
from src.repositories.notification_repository import NotificationRepository
from src.schemas.notification import SendNotificationRequest
from src.services.smtp_client import SMTPClient
from src.services.template_engine import TemplateEngine

logger = logging.getLogger(__name__)

# --- Prometheus metrics ---
notifications_sent_total = Counter(
    "notifications_sent_total",
    "Total notifications successfully sent",
    ["tenant_id", "channel", "template_id"],
)
notifications_failed_total = Counter(
    "notifications_failed_total",
    "Total notifications that failed after all retries",
    ["tenant_id", "channel", "template_id"],
)
notification_delivery_duration_seconds = Histogram(
    "notification_delivery_duration_seconds",
    "Notification delivery duration in seconds",
    ["channel"],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)

MAX_RETRIES = 3
BACKOFF_SECONDS = [1.0, 2.0, 4.0]


class NotificationService:
    def __init__(
        self,
        db: AsyncSession,
        smtp_client: SMTPClient,
        template_engine: TemplateEngine,
    ) -> None:
        self._db = db
        self._smtp = smtp_client
        self._templates = template_engine
        self._repo = NotificationRepository(db)

    async def create_notification(
        self,
        request: SendNotificationRequest,
        tenant_id: uuid.UUID,
        idempotency_key: str | None,
    ) -> Notification:
        # Idempotency check
        if idempotency_key:
            existing = await self._repo.find_by_idempotency_key(tenant_id, idempotency_key)
            if existing:
                logger.info(
                    "Idempotent request — returning existing notification",
                    extra={"notification_id": str(existing.id)},
                )
                return existing

        notification = await self._repo.create(
            tenant_id=tenant_id,
            channel=request.channel,
            template_id=request.template_id,
            recipient_address=request.recipient.address,
            recipient_name=request.recipient.name,
            payload=request.payload,
            idempotency_key=idempotency_key,
        )
        logger.info(
            "Notification created",
            extra={
                "notification_id": str(notification.id),
                "channel": notification.channel,
                "template_id": notification.template_id,
            },
        )
        return notification

    async def process_notification(self, notification_id: uuid.UUID) -> None:
        """Fire-and-forget delivery with retry logic."""
        from src.database import async_session_factory

        async with async_session_factory() as session:
            repo = NotificationRepository(session)
            notification = await repo.get_by_id_internal(notification_id)

            if notification is None:
                logger.error(
                    "Notification not found for processing",
                    extra={"notification_id": str(notification_id)},
                )
                return

            if notification.channel == "sms":
                # SMS is stubbed for MVP — just leave as queued
                logger.info(
                    "SMS channel is stubbed for MVP",
                    extra={"notification_id": str(notification_id)},
                )
                return

            await self._deliver_with_retry(repo, notification)

    async def _deliver_with_retry(
        self, repo: NotificationRepository, notification: Notification
    ) -> None:
        tenant_labels = {
            "tenant_id": str(notification.tenant_id),
            "channel": notification.channel,
            "template_id": notification.template_id,
        }

        for attempt in range(MAX_RETRIES):
            try:
                start = asyncio.get_event_loop().time()

                # Render template
                variables = dict(notification.payload)
                if notification.recipient_name:
                    variables.setdefault("recipient_name", notification.recipient_name)

                html_body = self._templates.render(notification.template_id, variables)

                # Send via SMTP
                await self._smtp.send_email(
                    to=notification.recipient_address,
                    subject=f"Order Confirmation - {variables.get('order_reference', '')}",
                    html_body=html_body,
                )

                duration = asyncio.get_event_loop().time() - start
                notification_delivery_duration_seconds.labels(channel=notification.channel).observe(
                    duration
                )

                # Update status to sent
                await repo.update_status(
                    notification.id,
                    status="sent",
                    delivered_at=datetime.now(tz=UTC),
                )
                notifications_sent_total.labels(**tenant_labels).inc()
                logger.info(
                    "Notification delivered",
                    extra={"notification_id": str(notification.id), "attempt": attempt + 1},
                )
                return

            except Exception as exc:
                retry_count = attempt + 1
                logger.warning(
                    "Notification delivery attempt failed",
                    extra={
                        "notification_id": str(notification.id),
                        "attempt": attempt + 1,
                        "error_type": type(exc).__name__,
                    },
                )
                if attempt < MAX_RETRIES - 1:
                    await repo.update_status(
                        notification.id,
                        status="queued",
                        retry_count=retry_count,
                    )
                    await asyncio.sleep(BACKOFF_SECONDS[attempt])
                else:
                    # Exhausted all retries — mark as failed
                    await repo.update_status(
                        notification.id,
                        status="failed",
                        retry_count=retry_count,
                    )
                    notifications_failed_total.labels(**tenant_labels).inc()
                    logger.error(
                        "Notification failed after all retries",
                        extra={"notification_id": str(notification.id)},
                    )
