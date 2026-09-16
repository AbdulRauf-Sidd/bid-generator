import uuid as uuid_module

from fastapi import Header, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User


async def get_current_user_id(
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
) -> uuid_module.UUID:
    if not x_user_id:
        raise HTTPException(status_code=401, detail="Missing X-User-Id header")

    try:
        return uuid_module.UUID(x_user_id)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="Invalid X-User-Id header") from exc


async def ensure_current_user(db: AsyncSession, user_id: uuid_module.UUID) -> User:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user
