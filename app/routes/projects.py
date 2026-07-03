import uuid as uuid_module
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import ensure_current_user, get_current_user_id
from app.core.database import get_db
from app.models import Profile, ReferenceProject
from app.schemas import ReferenceProjectCreate, ReferenceProjectResponse
from app.services.mistral import embed_text

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("", response_model=list[ReferenceProjectResponse], summary="List reference projects")
async def list_projects(
    profile_id: Optional[uuid_module.UUID] = None,
    current_user_id: uuid_module.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    await ensure_current_user(db, current_user_id)
    query = (
        select(ReferenceProject)
        .where(ReferenceProject.user_id == current_user_id)
        .order_by(ReferenceProject.created_at.desc())
    )
    if profile_id:
        query = query.where(ReferenceProject.profile_id == profile_id)
    result = await db.execute(query)
    return result.scalars().all()


@router.post("", response_model=ReferenceProjectResponse, summary="Add a reference project and generate its embedding")
async def create_project(
    data: ReferenceProjectCreate,
    current_user_id: uuid_module.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    await ensure_current_user(db, current_user_id)
    if data.profile_id:
        profile_result = await db.execute(
            select(Profile.id).where(Profile.id == data.profile_id, Profile.user_id == current_user_id)
        )
        if profile_result.scalar_one_or_none() is None:
            raise HTTPException(status_code=404, detail="Profile not found")

    embed_input = f"{data.title}\n{data.description}\n{' '.join(data.skills or [])}\n{' '.join(data.tech_stack or [])}"
    embedding = await embed_text(embed_input)

    project = ReferenceProject(
        user_id=current_user_id,
        profile_id=data.profile_id,
        title=data.title,
        description=data.description,
        skills=data.skills,
        tech_stack=data.tech_stack,
        outcome=data.outcome,
        embedding=embedding,
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return project


@router.get("/{project_id}", response_model=ReferenceProjectResponse, summary="Get a reference project by ID")
async def get_project(
    project_id: uuid_module.UUID,
    current_user_id: uuid_module.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    await ensure_current_user(db, current_user_id)
    result = await db.execute(
        select(ReferenceProject).where(
            ReferenceProject.id == project_id,
            ReferenceProject.user_id == current_user_id,
        )
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Reference project not found")
    return project


@router.put("/{project_id}", response_model=ReferenceProjectResponse, summary="Update a reference project")
async def update_project(
    project_id: uuid_module.UUID,
    data: ReferenceProjectCreate,
    current_user_id: uuid_module.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    await ensure_current_user(db, current_user_id)
    result = await db.execute(
        select(ReferenceProject).where(
            ReferenceProject.id == project_id,
            ReferenceProject.user_id == current_user_id,
        )
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Reference project not found")

    if data.profile_id:
        profile_result = await db.execute(
            select(Profile.id).where(Profile.id == data.profile_id, Profile.user_id == current_user_id)
        )
        if profile_result.scalar_one_or_none() is None:
            raise HTTPException(status_code=404, detail="Profile not found")

    embed_input = f"{data.title}\n{data.description}\n{' '.join(data.skills or [])}\n{' '.join(data.tech_stack or [])}"
    embedding = await embed_text(embed_input)

    project.profile_id = data.profile_id
    project.title = data.title
    project.description = data.description
    project.skills = data.skills
    project.tech_stack = data.tech_stack
    project.outcome = data.outcome
    project.embedding = embedding

    await db.commit()
    await db.refresh(project)
    return project


@router.delete("/{project_id}", summary="Delete a reference project")
async def delete_project(
    project_id: uuid_module.UUID,
    current_user_id: uuid_module.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    await ensure_current_user(db, current_user_id)
    result = await db.execute(
        select(ReferenceProject).where(
            ReferenceProject.id == project_id,
            ReferenceProject.user_id == current_user_id,
        )
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Reference project not found")
    await db.delete(project)
    await db.commit()
    return {"message": "Reference project deleted"}
