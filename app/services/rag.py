from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ReferenceProject

DEFAULT_SYSTEM_PROMPT = (
    "You are a top-rated Upwork freelancer with a 100% Job Success Score. "
    "You write bids that win because they are specific, client-focused, and never generic. "
    "You never use hollow filler phrases or copy-paste language."
)

DEFAULT_BID_GENERATION_PROMPT = """Write a compelling Upwork bid proposal for this job.

Use the job details, my past relevant projects, and memory context provided.

Write a 200-300 word bid proposal that:
- Opens with a specific hook that addresses their exact problem
- Never starts with "I am writing to express..."
- Naturally weaves in experience from my past projects as proof of capability
- Shows you understand what they actually need
- Is conversational and direct, not corporate
- Ends with a confident, low-friction call-to-action

Output the bid text only, no extra commentary."""

DEFAULT_QUESTIONS_PROMPT = (
    "Answer each of the client's screening questions directly, in the same confident, "
    "conversational voice as the bid. Keep each answer concise (1-3 sentences) and specific "
    "to this job. Pair every answer with the exact original question text."
)


async def find_similar_projects(
    db: AsyncSession,
    embedding: list[float],
    top_k: int,
    user_id: UUID,
    profile_id: UUID | None = None,
) -> list[dict]:
    query = (
        select(
            ReferenceProject.id,
            ReferenceProject.title,
            ReferenceProject.description,
            ReferenceProject.skills,
            ReferenceProject.tech_stack,
            ReferenceProject.outcome,
        )
        .where(
            ReferenceProject.embedding.is_not(None),
            ReferenceProject.user_id == user_id,
        )
    )

    if profile_id:
        query = query.where(ReferenceProject.profile_id == profile_id)

    query = query.order_by(ReferenceProject.embedding.cosine_distance(embedding)).limit(top_k)

    result = await db.execute(query)
    return [dict(row._mapping) for row in result.fetchall()]


def build_user_message(
    job: dict,
    bid_generation_prompt: str,
    similar_projects: list[dict],
    memories: list[dict],
    profile: dict | None = None,
) -> str:
    skills_str = ", ".join(job.get("skills") or []) or "Not specified"
    budget_str = job.get("budget") or "Not specified"

    profile_block = ""
    has_profile_name = bool(profile and profile.get("name"))
    # A bare name is not "supporting context" — it gives the model no grounds for a
    # background claim. Only a bio or skills list counts as real background material.
    has_background_context = bool(profile and (profile.get("bio") or profile.get("skills")))
    if has_profile_name or has_background_context:
        profile_block = "\n\n---\n## Freelancer Profile\n"
        if profile.get("name"):
            profile_block += f"**Name:** {profile['name']}\n"
        if profile.get("bio"):
            profile_block += f"**Bio:** {profile['bio']}\n"
        p_skills = ", ".join(profile.get("skills") or [])
        if p_skills:
            profile_block += f"**Skills:** {p_skills}\n"
        profile_block += "\n---\n"

    projects_block = ""
    if similar_projects:
        projects_block = "\n\n---\n## My Past Relevant Projects (reference these as proof of experience in the bid):\n"
        for i, project in enumerate(similar_projects, 1):
            projects_block += f"\n### Project {i}: {project['title']}\n"
            projects_block += f"**Description:** {project['description']}\n"
            p_skills = ", ".join(project.get("skills") or [])
            if p_skills:
                projects_block += f"**Skills Used:** {p_skills}\n"
            tech = ", ".join(project.get("tech_stack") or [])
            if tech:
                projects_block += f"**Tech Stack:** {tech}\n"
            if project.get("outcome"):
                projects_block += f"**Outcome:** {project['outcome']}\n"
        projects_block += "\n---\n"

    memory_block = ""
    if memories:
        memory_block = (
            "\n\n---\n## Recent AI Memory (tone/phrasing continuity only. These are past "
            "AI-drafted messages, NOT verified portfolio evidence. Never treat any project, "
            "client, or experience claim inside them as real or reusable in a 'Relevant work' "
            "list unless it also appears in 'My Past Relevant Projects' or 'Freelancer Profile' "
            "above.):\n"
        )
        for i, memory in enumerate(memories, 1):
            memory_block += f"\n### Memory {i}\n"
            if memory.get("user_instruction"):
                memory_block += f"**User Edit:** {memory['user_instruction']}\n"
            if memory.get("ai_response"):
                memory_block += f"**AI Response:**\n{memory['ai_response']}\n"
        memory_block += "\n---\n"

    grounding_note = ""
    if not has_background_context and not similar_projects:
        grounding_note = (
            "\n\n---\nNo bio, skills, or past project data has been provided for this bid "
            "(a name alone, if shown above, is not background material). Do not invent a "
            "background, skills, past clients, specific past projects, or a 'Relevant work' "
            "list under any circumstances. Write paragraph 2 as a brief, generic statement of "
            "capability for this type of work without any specific fabricated claims, and "
            "skip the Relevant work list entirely.\n---\n"
        )

    return f"""{bid_generation_prompt}

## Current Job

**Title:** {job['title']}
**Budget:** {budget_str}
**Required Skills:** {skills_str}

**Job Description:**
{job['description']}
{profile_block}
{projects_block}
{memory_block}
{grounding_note}"""


def build_messages(
    job: dict,
    prompts: dict[str, str],
    similar_projects: list[dict],
    memories: list[dict],
    profile: dict | None = None,
) -> list[dict]:
    user_message = build_user_message(
        job=job,
        bid_generation_prompt=prompts.get("bid_generation") or DEFAULT_BID_GENERATION_PROMPT,
        similar_projects=similar_projects,
        memories=memories,
        profile=profile,
    )
    return [
        {
            "role": "system",
            "content": prompts.get("system") or DEFAULT_SYSTEM_PROMPT,
        },
        {"role": "user", "content": user_message},
    ]


def build_revision_messages(
    job: dict,
    current_bid: str,
    instruction: str,
    prompts: dict[str, str],
) -> list[dict]:
    skills_str = ", ".join(job.get("skills") or []) or "Not specified"
    budget_str = job.get("budget") or "Not specified"

    return [
        {
            "role": "system",
            "content": prompts.get("system") or DEFAULT_SYSTEM_PROMPT,
        },
        {
            "role": "user",
            "content": f"""{prompts.get("bid_generation") or DEFAULT_BID_GENERATION_PROMPT}

## Current Job

**Title:** {job['title']}
**Budget:** {budget_str}
**Required Skills:** {skills_str}

**Job Description:**
{job['description']}

## Current Bid Version

{current_bid}

## User's Requested Edits

{instruction}

Rewrite the bid to apply the requested edits. Keep useful details from the current version unless the instruction changes them. Output only the complete revised bid text, with no commentary.""",
        },
    ]


def build_question_messages(
    job: dict,
    questions: list[str],
    prompts: dict[str, str],
) -> list[dict]:
    questions_block = "\n".join(f"{i}. {q}" for i, q in enumerate(questions, 1))

    return [
        {
            "role": "system",
            "content": prompts.get("system") or DEFAULT_SYSTEM_PROMPT,
        },
        {
            "role": "user",
            "content": f"""{prompts.get("questions") or DEFAULT_QUESTIONS_PROMPT}

## Job

**Title:** {job['title']}

**Job Description:**
{job['description']}

## Client's Screening Questions

{questions_block}

Answer every question listed above, in order.""",
        },
    ]
