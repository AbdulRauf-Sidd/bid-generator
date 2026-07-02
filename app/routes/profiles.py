import uuid as uuid_module

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import ensure_current_user, get_current_user_id
from app.core.database import get_db
from app.models import Profile
from app.schemas import ProfileCreate, ProfileResponse, ProfileUpdate

router = APIRouter(prefix="/profiles", tags=["profiles"])


@router.get("", response_model=list[ProfileResponse], summary="List all profiles")
async def list_profiles(
    current_user_id: uuid_module.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    await ensure_current_user(db, current_user_id)
    result = await db.execute(
        select(Profile)
        .where(Profile.user_id == current_user_id)
        .order_by(Profile.created_at.asc())
    )
    return result.scalars().all()


@router.post("", response_model=ProfileResponse, summary="Create a new profile")
async def create_profile(
    data: ProfileCreate,
    current_user_id: uuid_module.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    await ensure_current_user(db, current_user_id)
    profile = Profile(
        user_id=current_user_id,
        name=data.name.strip(),
        bio=data.bio,
        skills=data.skills,
    )
    db.add(profile)
    await db.commit()
    await db.refresh(profile)
    return profile


@router.get("/{profile_id}", response_model=ProfileResponse, summary="Get a profile by ID")
async def get_profile(
    profile_id: uuid_module.UUID,
    current_user_id: uuid_module.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    await ensure_current_user(db, current_user_id)
    result = await db.execute(
        select(Profile).where(Profile.id == profile_id, Profile.user_id == current_user_id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    return profile


@router.put("/{profile_id}", response_model=ProfileResponse, summary="Update a profile")
async def update_profile(
    profile_id: uuid_module.UUID,
    data: ProfileUpdate,
    current_user_id: uuid_module.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    await ensure_current_user(db, current_user_id)
    result = await db.execute(
        select(Profile).where(Profile.id == profile_id, Profile.user_id == current_user_id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    if data.name is not None:
        profile.name = data.name.strip()
    if data.bio is not None:
        profile.bio = data.bio
    if data.skills is not None:
        profile.skills = data.skills

    await db.commit()
    await db.refresh(profile)
    return profile


@router.delete("/{profile_id}", summary="Delete a profile")
async def delete_profile(
    profile_id: uuid_module.UUID,
    current_user_id: uuid_module.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    await ensure_current_user(db, current_user_id)
    result = await db.execute(
        select(Profile).where(Profile.id == profile_id, Profile.user_id == current_user_id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    await db.delete(profile)
    await db.commit()
    return {"message": "Profile deleted"}
