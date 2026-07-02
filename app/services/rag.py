from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

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


async def find_similar_projects(
    db: AsyncSession,
    embedding: list[float],
    top_k: int,
    user_id: str,
    profile_id: str | None = None,
) -> list[dict]:
    embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"

    where_clause = "WHERE embedding IS NOT NULL AND user_id = CAST(:user_id AS UUID)"
    params: dict = {"embedding": embedding_str, "top_k": top_k, "user_id": user_id}

    if profile_id:
        where_clause += " AND (profile_id = CAST(:profile_id AS UUID) OR profile_id IS NULL)"
        params["profile_id"] = profile_id

    result = await db.execute(
        text(f"""
            SELECT id, title, description, skills, tech_stack, outcome
            FROM reference_projects
            {where_clause}
            ORDER BY embedding <=> CAST(:embedding AS vector)
            LIMIT :top_k
        """),
        params,
    )

    return [dict(row._mapping) for row in result.fetchall()]


def build_user_message(
    job: dict,
    bid_generation_prompt: str,
    similar_projects: list[dict],
    memories: list[dict],
) -> str:
    skills_str = ", ".join(job.get("skills") or []) or "Not specified"
    budget_str = job.get("budget") or "Not specified"

    client_info = job.get("client_info") or {}
    client_parts = []
    if client_info.get("country"):
        client_parts.append(f"Country: {client_info['country']}")
    if client_info.get("hire_rate"):
        client_parts.append(f"Hire Rate: {client_info['hire_rate']}")
    if client_info.get("reviews") is not None:
        client_parts.append(f"Rating: {client_info['reviews']}/5")
    if client_info.get("total_spent"):
        client_parts.append(f"Total Spent: {client_info['total_spent']}")
    client_str = " | ".join(client_parts) or "Not provided"

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
        memory_block = "\n\n---\n## Recent AI Memory (use for continuity and style context only):\n"
        for i, memory in enumerate(memories, 1):
            memory_block += f"\n### Memory {i}\n"
            if memory.get("user_instruction"):
                memory_block += f"**User Edit:** {memory['user_instruction']}\n"
            if memory.get("ai_response"):
                memory_block += f"**AI Response:**\n{memory['ai_response']}\n"
        memory_block += "\n---\n"

    return f"""{bid_generation_prompt}

## Current Job

**Title:** {job['title']}
**Budget:** {budget_str}
**Required Skills:** {skills_str}
**Client:** {client_str}

**Job Description:**
{job['description']}
{projects_block}
{memory_block}"""


def build_messages(
    job: dict,
    prompts: dict[str, str],
    similar_projects: list[dict],
    memories: list[dict],
) -> list[dict]:
    user_message = build_user_message(
        job=job,
        bid_generation_prompt=prompts.get("bid_generation") or DEFAULT_BID_GENERATION_PROMPT,
        similar_projects=similar_projects,
        memories=memories,
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
