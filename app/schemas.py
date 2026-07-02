from typing import Optional, List
from datetime import datetime
from uuid import UUID

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator


# ── Auth ─────────────────────────────────────────────────────────────────────


class GoogleAuthRequest(BaseModel):
    id_token: str = Field(
        min_length=1,
        validation_alias=AliasChoices("id_token", "credential"),
    )

    model_config = ConfigDict(populate_by_name=True)


class UserResponse(BaseModel):
    id: UUID
    google_sub: str
    email: str
    email_verified: bool
    name: Optional[str] = None
    given_name: Optional[str] = None
    family_name: Optional[str] = None
    picture: Optional[str] = None
    locale: Optional[str] = None
    provider: str
    last_login_at: datetime
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class GoogleAuthResponse(BaseModel):
    user: UserResponse
    message: str


# ── Profile ──────────────────────────────────────────────────────────────────

class ProfileCreate(BaseModel):
    name: str
    bio: Optional[str] = None
    skills: Optional[List[str]] = None


class ProfileUpdate(BaseModel):
    name: Optional[str] = None
    bio: Optional[str] = None
    skills: Optional[List[str]] = None


class ProfileResponse(BaseModel):
    id: UUID
    user_id: Optional[UUID] = None
    name: str
    bio: Optional[str] = None
    skills: Optional[List[str]] = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Reference Project ─────────────────────────────────────────────────────────

class ReferenceProjectCreate(BaseModel):
    profile_id: Optional[UUID] = None
    title: str
    description: str
    skills: Optional[List[str]] = None
    tech_stack: Optional[List[str]] = None
    outcome: Optional[str] = None


class ReferenceProjectResponse(BaseModel):
    id: UUID
    user_id: Optional[UUID] = None
    profile_id: Optional[UUID] = None
    title: str
    description: str
    skills: Optional[List[str]] = None
    tech_stack: Optional[List[str]] = None
    outcome: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Job / Bid ─────────────────────────────────────────────────────────────────

class ClientInfo(BaseModel):
    country: Optional[str] = None
    hire_rate: Optional[str] = None
    reviews: Optional[float] = None
    total_spent: Optional[str] = None
    member_since: Optional[str] = None


class JobCreate(BaseModel):
    profile_id: Optional[UUID] = None
    title: str
    description: str
    budget: Optional[str] = None
    skills: Optional[List[str]] = None
    client_info: Optional[ClientInfo] = None


class BidSeed(BaseModel):
    title: str
    description: str
    budget: Optional[str] = None
    skills: Optional[List[str]] = None
    client_info: Optional[ClientInfo] = None
    bid_text: str


class JobResponse(BaseModel):
    id: UUID
    user_id: Optional[UUID] = None
    profile_id: Optional[UUID] = None
    title: str
    description: str
    budget: Optional[str] = None
    skills: Optional[List[str]] = None
    client_info: Optional[dict] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class BidResponse(BaseModel):
    id: UUID
    user_id: Optional[UUID] = None
    job_id: UUID
    bid_text: str
    is_manual: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class BidRevisionRequest(BaseModel):
    instruction: str = Field(min_length=1, max_length=4000)

    @field_validator("instruction")
    @classmethod
    def instruction_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("instruction must not be blank")
        return value


class SeedResponse(BaseModel):
    job_id: UUID
    bid_id: UUID
    message: str


# ── Conversation view ─────────────────────────────────────────────────────────

class ConversationMessage(BaseModel):
    memory_type: str
    bid: BidResponse
    user_instruction: Optional[str] = None

    model_config = {"from_attributes": True}


class ConversationResponse(BaseModel):
    job: JobResponse
    messages: List[ConversationMessage]


# ── Prompt ────────────────────────────────────────────────────────────────────

class PromptCreate(BaseModel):
    type: str
    prompt: str


class PromptUpdate(BaseModel):
    prompt: str


class PromptResponse(BaseModel):
    id: UUID
    user_id: Optional[UUID] = None
    type: str
    prompt: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── Memory ────────────────────────────────────────────────────────────────────

class MemoryResponse(BaseModel):
    id: UUID
    user_id: Optional[UUID] = None
    job_id: Optional[UUID] = None
    bid_id: Optional[UUID] = None
    user_message: str
    user_instruction: Optional[str] = None
    ai_response: Optional[str] = None
    memory_type: str
    metadata: Optional[dict] = Field(
        default=None,
        validation_alias="memory_metadata",
        serialization_alias="metadata",
    )
    created_at: datetime

    model_config = {"from_attributes": True}
