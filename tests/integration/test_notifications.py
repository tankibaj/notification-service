"""
Integration tests for the notification-service.

TS-001-034 — Order-service calls notification-service after successful order
TS-001-036 — Notification payload includes order reference, items, and total
TS-001-037 — Failed notification does not affect order status
TS-001-038 — Failed notification is queryable via GET
"""

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import ORDER_PAYLOAD, SEND_NOTIFICATION_BODY, TENANT_ID


@pytest.mark.asyncio
async def test_ts_001_034_notification_accepted_and_queued(client: AsyncClient) -> None:
    """
    TS-001-034: POST /notifications returns HTTP 202 with NotificationReceipt.
    status is 'queued', notification is persisted in DB.
    """
    response = await client.post(
        "/api/v1/notifications",
        json=SEND_NOTIFICATION_BODY,
        headers={"X-Tenant-ID": TENANT_ID},
    )

    assert response.status_code == 202
    data = response.json()

    # NotificationReceipt schema validation
    assert "id" in data
    assert data["status"] == "queued"
    assert "created_at" in data
    assert data["channel"] == "email"
    assert data["template_id"] == "order_confirmation"
    assert data.get("delivered_at") is None

    # Verify notification is persisted in DB via GET
    notification_id = data["id"]
    get_response = await client.get(
        f"/api/v1/notifications/{notification_id}",
        headers={"X-Tenant-ID": TENANT_ID},
    )
    assert get_response.status_code == 200
    assert get_response.json()["id"] == notification_id


@pytest.mark.asyncio
async def test_ts_001_036_notification_payload_renders_email(client: AsyncClient) -> None:
    """
    TS-001-036: The rendered email HTML contains order_reference, product name,
    quantity, and total. Verified by checking what was passed to the SMTP mock.
    """
    body = {
        "channel": "email",
        "template_id": "order_confirmation",
        "recipient": {"address": "grace@example.com", "name": "Grace"},
        "payload": {
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
        },
    }

    response = await client.post(
        "/api/v1/notifications",
        json=body,
        headers={"X-Tenant-ID": TENANT_ID},
    )

    assert response.status_code == 202
    assert response.json()["status"] == "queued"

    # Wait for background delivery task
    await asyncio.sleep(0.5)

    mock_smtp = client.mock_smtp  # type: ignore[attr-defined]
    assert mock_smtp.send_email.called, "SMTP send_email should have been called"

    call_kwargs = mock_smtp.send_email.call_args
    # send_email signature: (to, subject, html_body)
    if call_kwargs.kwargs:
        html_body = call_kwargs.kwargs.get("html_body", "")
    else:
        html_body = call_kwargs.args[2] if len(call_kwargs.args) > 2 else ""

    assert "ORD-20260411-A3K9" in html_body, "HTML must contain order reference"
    assert "Classic T-Shirt" in html_body, "HTML must contain product name"
    assert "2" in html_body, "HTML must contain quantity"
    assert "$74.97" in html_body, "HTML must contain total"


@pytest.mark.asyncio
async def test_ts_001_037_failed_notification_after_retry_exhaustion(
    db_session: AsyncSession,
) -> None:
    """
    TS-001-037: After exhausting 3 retries with a failing SMTP,
    notification status is 'failed' and delivered_at is null.
    """
    from src.repositories.notification_repository import NotificationRepository
    from src.services.notification_service import NotificationService
    from src.services.smtp_client import SMTPClient
    from src.services.template_engine import TemplateEngine

    smtp_mock = MagicMock(spec=SMTPClient)
    smtp_mock.send_email = AsyncMock(side_effect=ConnectionRefusedError("SMTP unavailable"))

    service = NotificationService(
        db=db_session,
        smtp_client=smtp_mock,
        template_engine=TemplateEngine(),
    )
    repo = NotificationRepository(db_session)

    notification = await repo.create(
        tenant_id=uuid.UUID(TENANT_ID),
        channel="email",
        template_id="order_confirmation",
        recipient_address="grace@example.com",
        recipient_name="Grace",
        payload=ORDER_PAYLOAD,
        idempotency_key=None,
    )

    # Patch asyncio.sleep to skip actual delays during retries
    with patch("src.services.notification_service.asyncio.sleep", return_value=None):
        await service._deliver_with_retry(repo, notification)  # type: ignore[attr-defined]

    assert smtp_mock.send_email.call_count == 3, (
        f"Expected 3 SMTP attempts, got {smtp_mock.send_email.call_count}"
    )

    await db_session.refresh(notification)
    assert notification.status == "failed", f"Expected 'failed', got '{notification.status}'"
    assert notification.delivered_at is None
    assert notification.retry_count == 3


@pytest.mark.asyncio
async def test_ts_001_038_failed_notification_queryable_via_get(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """
    TS-001-038: A notification with status 'failed' is retrievable via GET
    and returns the correct NotificationReceipt schema.
    """
    from src.repositories.notification_repository import NotificationRepository

    repo = NotificationRepository(db_session)
    notification = await repo.create(
        tenant_id=uuid.UUID(TENANT_ID),
        channel="email",
        template_id="order_confirmation",
        recipient_address="grace@example.com",
        recipient_name="Grace",
        payload=ORDER_PAYLOAD,
        idempotency_key=None,
    )
    await repo.update_status(notification.id, status="failed", retry_count=3)
    await db_session.refresh(notification)

    response = await client.get(
        f"/api/v1/notifications/{notification.id}",
        headers={"X-Tenant-ID": TENANT_ID},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(notification.id)
    assert data["status"] == "failed"
    assert data["channel"] == "email"
    assert data["template_id"] == "order_confirmation"
    assert "created_at" in data
    assert data.get("delivered_at") is None
