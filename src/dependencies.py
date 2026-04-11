import uuid
from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import async_session_factory


async def get_db() -> AsyncGenerator[AsyncSession]:
    async with async_session_factory() as session:
        yield session


async def get_tenant_id(
    x_tenant_id: Annotated[str | None, Header(alias="X-Tenant-ID")] = None,
) -> uuid.UUID:
    if x_tenant_id is None:
        raise HTTPException(status_code=422, detail="X-Tenant-ID header is required")
    try:
        return uuid.UUID(x_tenant_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="X-Tenant-ID must be a valid UUID") from None
