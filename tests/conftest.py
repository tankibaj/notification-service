import uuid
from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.services.smtp_client import SMTPClient

# ---- Test database URL (local postgres container) ----
TEST_DATABASE_URL = "postgresql+asyncpg://app:app@localhost:5434/app"


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Provide a clean DB session per test.
    Creates a fresh engine+session per test to avoid event-loop conflicts.
    Truncates the notifications table in teardown.
    """
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with factory() as session:
        yield session
        await session.execute(text("TRUNCATE TABLE notifications RESTART IDENTITY CASCADE"))
        await session.commit()

    await engine.dispose()


@pytest.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """
    HTTP test client with:
    - Real PostgreSQL DB (test container) via overridden get_db
    - Mock SMTP client injected via overridden get_notification_service
    """
    from src.api.v1.notifications import get_notification_service
    from src.dependencies import get_db
    from src.services.notification_service import NotificationService
    from src.services.template_engine import TemplateEngine
    from src.main import create_app

    smtp = MagicMock(spec=SMTPClient)
    smtp.send_email = AsyncMock(return_value=None)
    smtp.host = "mock"
    smtp.port = 1025
    smtp.sender = "noreply@example.com"

    app = create_app()

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    def override_get_notification_service() -> NotificationService:
        return NotificationService(
            db=db_session,
            smtp_client=smtp,
            template_engine=TemplateEngine(),
        )

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_notification_service] = override_get_notification_service

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        ac.mock_smtp = smtp  # type: ignore[attr-defined]
        yield ac


# ---- Shared constants ----

TENANT_ID = str(uuid.uuid4())

ORDER_PAYLOAD: dict[str, Any] = {
    "order_reference": "ORD-20260411-A3K9",
    "lines": [
        {
            "product_name": "Classic T-Shirt",
            "variant_label": "Small",
            "quantity": 2,
            "unit_price": "$29.99",
        }
    ],
    "total": "$74.97",
}

SEND_NOTIFICATION_BODY: dict[str, Any] = {
    "channel": "email",
    "template_id": "order_confirmation",
    "recipient": {
        "address": "grace@example.com",
        "name": "Grace",
    },
    "payload": ORDER_PAYLOAD,
}
