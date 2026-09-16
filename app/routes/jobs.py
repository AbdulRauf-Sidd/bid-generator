import json
import uuid as uuid_module
from typing import AsyncGenerator, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import or_, select

from app.core.config import settings
from app.core.auth import ensure_current_user, get_current_user_id
from app.core.database import get_db, AsyncSessionLocal
from app.models import Job, Bid, Prompt, AiMemory, Profile
from app.schemas import (
    BidRevisionRequest,
    BidResponse,
    ConversationMessage,
    ConversationResponse,
    JobCreate,
    JobResponse,
)
from app.services.llm import answer_questions, stream_chat
from app.services.mistral import embed_text
from app.services.rag import (
    build_messages,
    build_question_messages,
    build_revision_messages,
    find_similar_projects,
)

router = APIRouter(prefix="/jobs", tags=["jobs"])


async def _bid_stream(
    job_id: uuid_module.UUID,
    user_id: uuid_module.UUID,
    messages: list[dict],
    memory_user_message: str,
    memory_type: str = "bid_generation",
    memory_metadata: dict | None = None,
    user_instruction: str | None = None,
    question_messages: list[dict] | None = None,
) -> AsyncGenerator[bytes, None]:
    full_text = ""
    async for chunk in stream_chat(messages):
        full_text += chunk
        yield f"data: {json.dumps({'type': 'chunk', 'content': chunk})}\n\n".encode()

    answers: list[dict] = []
    if question_messages:
        try:
            answers = await answer_questions(question_messages)
        except Exception:
            answers = []

    async with AsyncSessionLocal() as save_db:
        bid = Bid(
            user_id=user_id,
            job_id=job_id,
            bid_text=full_text,
            is_manual=False,
            answers=answers or None,
        )
        save_db.add(bid)
        await save_db.flush()

        memory = AiMemory(
            user_id=user_id,
            job_id=job_id,
            bid_id=bid.id,
            user_message=memory_user_message,
            user_instruction=user_instruction,
            ai_response=full_text,
            memory_type=memory_type,
            memory_metadata=memory_metadata or {"source": "generate_bid"},
        )
        save_db.add(memory)
        await save_db.commit()
        await save_db.refresh(bid)

    yield f"data: {json.dumps({'type': 'done', 'bid_id': str(bid.id), 'job_id': str(job_id), 'answers': answers})}\n\n".encode()


async def _load_prompts(
    db: AsyncSession,
    user_id: uuid_module.UUID,
    prompt_types: list[str],
) -> dict[str, str]:
    result = await db.execute(
        select(Prompt).where(
            Prompt.type.in_(prompt_types),
            or_(Prompt.user_id.is_(None), Prompt.user_id == user_id),
        )
    )
    prompts: dict[str, str] = {}
    for prompt in result.scalars().all():
        if prompt.type not in prompts or prompt.user_id == user_id:
            prompts[prompt.type] = prompt.prompt
    return prompts


@router.post("/generate-bid", summary="Submit an Upwork job and stream back an AI-generated bid")
async def generate_bid(
    data: JobCreate,
    current_user_id: uuid_module.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    await ensure_current_user(db, current_user_id)
    profile: Profile | None = None
    if data.profile_id:
        profile_result = await db.execute(
            select(Profile).where(Profile.id == data.profile_id, Profile.user_id == current_user_id)
        )
        profile = profile_result.scalar_one_or_none()
        if profile is None:
            raise HTTPException(status_code=404, detail="Profile not found")

    embed_input = f"{data.title}\n{data.description}\n{' '.join(data.skills or [])}"
    embedding = await embed_text(embed_input)

    job = Job(
        user_id=current_user_id,
        profile_id=data.profile_id,
        title=data.title,
        description=data.description,
        budget=data.budget,
        skills=data.skills,
        questions=data.questions,
        embedding=embedding,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    similar_projects = await find_similar_projects(
        db,
        embedding,
        settings.RAG_TOP_K,
        current_user_id,
        data.profile_id,
    )

    prompts = await _load_prompts(db, current_user_id, ["system", "bid_generation", "questions"])

    memory_query = (
        select(AiMemory)
        .join(Job, AiMemory.job_id == Job.id)
        .where(
            AiMemory.user_id == current_user_id,
            Job.user_id == current_user_id,
            AiMemory.ai_response.is_not(None),
        )
        .order_by(AiMemory.created_at.desc())
        .limit(settings.RAG_TOP_K)
    )
    if data.profile_id:
        memory_query = memory_query.where(Job.profile_id == data.profile_id)
    memory_result = await db.execute(memory_query)
    memories = [
        {
            "user_instruction": memory.user_instruction,
            "ai_response": memory.ai_response,
        }
        for memory in memory_result.scalars().all()
    ]

    profile_data = (
        {"name": profile.name, "bio": profile.bio, "skills": profile.skills}
        if profile is not None
        else None
    )

    job_data = data.model_dump(mode="json")
    prompt_messages = build_messages(job_data, prompts, similar_projects, memories, profile_data)
    memory_user_message = json.dumps({"job": job_data})

    question_messages = (
        build_question_messages(job_data, data.questions, prompts) if data.questions else None
    )

    return StreamingResponse(
        _bid_stream(
            job.id,
            current_user_id,
            prompt_messages,
            memory_user_message,
            question_messages=question_messages,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Job-ID": str(job.id)},
    )


@router.get("", response_model=list[JobResponse], summary="List all submitted jobs")
async def list_jobs(
    profile_id: Optional[uuid_module.UUID] = None,
    skip: int = 0,
    limit: int = 20,
    current_user_id: uuid_module.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    await ensure_current_user(db, current_user_id)
    query = (
        select(Job)
        .where(Job.user_id == current_user_id)
        .order_by(Job.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    if profile_id:
        query = query.where(Job.profile_id == profile_id)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/{job_id}", response_model=JobResponse, summary="Get a single job by ID")
async def get_job(
    job_id: uuid_module.UUID,
    current_user_id: uuid_module.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    await ensure_current_user(db, current_user_id)
    result = await db.execute(select(Job).where(Job.id == job_id, Job.user_id == current_user_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("/{job_id}/conversation", response_model=ConversationResponse, summary="Get ChatGPT-style conversation for a job")
async def get_job_conversation(
    job_id: uuid_module.UUID,
    current_user_id: uuid_module.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    await ensure_current_user(db, current_user_id)
    job_result = await db.execute(select(Job).where(Job.id == job_id, Job.user_id == current_user_id))
    job = job_result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    bids_result = await db.execute(
        select(Bid)
        .where(Bid.job_id == job_id, Bid.user_id == current_user_id)
        .order_by(Bid.created_at.asc())
    )
    bids = bids_result.scalars().all()

    memories_result = await db.execute(
        select(AiMemory)
        .where(AiMemory.job_id == job_id, AiMemory.user_id == current_user_id)
        .order_by(AiMemory.created_at.asc())
    )
    memories_by_bid = {str(m.bid_id): m for m in memories_result.scalars().all()}

    messages = []
    for bid in bids:
        memory = memories_by_bid.get(str(bid.id))
        messages.append(
            ConversationMessage(
                memory_type=memory.memory_type if memory else "bid_generation",
                bid=BidResponse.model_validate(bid),
                user_instruction=memory.user_instruction if memory else None,
            )
        )

    return ConversationResponse(job=JobResponse.model_validate(job), messages=messages)


@router.get("/{job_id}/bid", response_model=BidResponse, summary="Get the latest bid for a job")
async def get_job_bid(
    job_id: uuid_module.UUID,
    current_user_id: uuid_module.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    await ensure_current_user(db, current_user_id)
    job_result = await db.execute(select(Job.id).where(Job.id == job_id, Job.user_id == current_user_id))
    if job_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Job not found")

    result = await db.execute(
        select(Bid)
        .where(Bid.job_id == job_id, Bid.user_id == current_user_id)
        .order_by(Bid.created_at.desc())
    )
    bid = result.scalars().first()
    if not bid:
        raise HTTPException(status_code=404, detail="No bid found for this job")
    return bid


@router.get("/{job_id}/bids", response_model=list[BidResponse], summary="List every bid version for a job")
async def list_job_bids(
    job_id: uuid_module.UUID,
    current_user_id: uuid_module.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    await ensure_current_user(db, current_user_id)
    job_result = await db.execute(select(Job.id).where(Job.id == job_id, Job.user_id == current_user_id))
    if job_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Job not found")

    result = await db.execute(
        select(Bid)
        .where(Bid.job_id == job_id, Bid.user_id == current_user_id)
        .order_by(Bid.created_at.desc())
    )
    return result.scalars().all()


@router.post(
    "/{job_id}/bids/{bid_id}/revise",
    summary="Apply user edit instructions and stream a new bid version",
)
async def revise_bid(
    job_id: uuid_module.UUID,
    bid_id: uuid_module.UUID,
    data: BidRevisionRequest,
    current_user_id: uuid_module.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    await ensure_current_user(db, current_user_id)
    job_result = await db.execute(select(Job).where(Job.id == job_id, Job.user_id == current_user_id))
    job = job_result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    bid_result = await db.execute(
        select(Bid).where(
            Bid.id == bid_id,
            Bid.job_id == job_id,
            Bid.user_id == current_user_id,
        )
    )
    current_bid = bid_result.scalar_one_or_none()
    if not current_bid:
        raise HTTPException(status_code=404, detail="Bid not found for this job")

    prompts = await _load_prompts(db, current_user_id, ["system", "bid_generation"])
    job_data = {
        "title": job.title,
        "description": job.description,
        "budget": job.budget,
        "skills": job.skills,
    }
    prompt_messages = build_revision_messages(
        job=job_data,
        current_bid=current_bid.bid_text,
        instruction=data.instruction.strip(),
        prompts=prompts,
    )
    memory_user_message = json.dumps(
        {
            "job": job_data,
            "source_bid_id": str(current_bid.id),
            "edit_instruction": data.instruction.strip(),
        }
    )

    return StreamingResponse(
        _bid_stream(
            job.id,
            current_user_id,
            prompt_messages,
            memory_user_message,
            memory_type="bid_revision",
            memory_metadata={
                "source": "bid_revision",
                "source_bid_id": str(current_bid.id),
            },
            user_instruction=data.instruction.strip(),
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Job-ID": str(job.id)},
    )
