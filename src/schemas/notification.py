import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, field_validator


class RecipientSchema(BaseModel):
    address: str
    name: str | None = None


class SendNotificationRequest(BaseModel):
    channel: str
    template_id: str
    recipient: RecipientSchema
    payload: dict[str, Any]

    @field_validator("channel")
    @classmethod
    def validate_channel(cls, v: str) -> str:
        allowed = {"email", "sms"}
        if v not in allowed:
            raise ValueError(f"channel must be one of {allowed}")
        return v


class NotificationReceipt(BaseModel):
    id: uuid.UUID
    status: str
    channel: str | None = None
    template_id: str | None = None
    created_at: datetime
    delivered_at: datetime | None = None

    model_config = {"from_attributes": True}
