import uuid as uuid_module

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import ensure_current_user, get_current_user_id
from app.core.database import get_db
from app.models import AiMemory
from app.schemas import MemoryResponse

router = APIRouter(prefix="/memory", tags=["memory"])


@router.get("", response_model=list[MemoryResponse], summary="List stored AI memory entries")
async def list_memory(
    skip: int = 0,
    limit: int = 20,
    current_user_id: uuid_module.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    await ensure_current_user(db, current_user_id)
    result = await db.execute(
        select(AiMemory)
        .where(AiMemory.user_id == current_user_id)
        .order_by(AiMemory.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    return result.scalars().all()
