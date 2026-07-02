import uuid as uuid_module

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import ensure_current_user, get_current_user_id
from app.core.database import get_db
from app.models import Prompt
from app.schemas import PromptCreate, PromptResponse, PromptUpdate

router = APIRouter(prefix="/prompts", tags=["prompts"])


@router.get("", response_model=list[PromptResponse], summary="List editable AI prompts")
async def list_prompts(
    current_user_id: uuid_module.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    await ensure_current_user(db, current_user_id)
    result = await db.execute(
        select(Prompt)
        .where(or_(Prompt.user_id.is_(None), Prompt.user_id == current_user_id))
        .order_by(Prompt.type.asc(), Prompt.user_id.asc().nullsfirst())
    )

    prompts_by_type: dict[str, Prompt] = {}
    for prompt in result.scalars().all():
        if prompt.type not in prompts_by_type or prompt.user_id == current_user_id:
            prompts_by_type[prompt.type] = prompt

    user_prompts: list[Prompt] = []
    created_prompt = False
    for prompt in prompts_by_type.values():
        if prompt.user_id == current_user_id:
            user_prompts.append(prompt)
            continue

        user_prompt = Prompt(
            user_id=current_user_id,
            type=prompt.type,
            prompt=prompt.prompt,
        )
        db.add(user_prompt)
        user_prompts.append(user_prompt)
        created_prompt = True

    if created_prompt:
        await db.commit()
        for prompt in user_prompts:
            if prompt.id:
                await db.refresh(prompt)

    return sorted(user_prompts, key=lambda prompt: prompt.type)


@router.post("", response_model=PromptResponse, summary="Create an editable AI prompt")
async def create_prompt(
    data: PromptCreate,
    current_user_id: uuid_module.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    await ensure_current_user(db, current_user_id)
    prompt_type = data.type.strip()
    if not prompt_type:
        raise HTTPException(status_code=400, detail="Prompt type is required")

    existing = await db.execute(
        select(Prompt).where(Prompt.type == prompt_type, Prompt.user_id == current_user_id)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Prompt type already exists")

    prompt = Prompt(user_id=current_user_id, type=prompt_type, prompt=data.prompt)
    db.add(prompt)
    await db.commit()
    await db.refresh(prompt)
    return prompt


@router.put("/{prompt_id}", response_model=PromptResponse, summary="Update an editable AI prompt")
async def update_prompt(
    prompt_id: uuid_module.UUID,
    data: PromptUpdate,
    current_user_id: uuid_module.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    await ensure_current_user(db, current_user_id)
    result = await db.execute(
        select(Prompt).where(Prompt.id == prompt_id, Prompt.user_id == current_user_id)
    )
    prompt = result.scalar_one_or_none()
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")

    prompt.prompt = data.prompt
    await db.commit()
    await db.refresh(prompt)
    return prompt
