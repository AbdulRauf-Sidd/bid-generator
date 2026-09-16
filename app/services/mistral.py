from typing import AsyncGenerator

from mistralai.client import Mistral
from pydantic import BaseModel

from app.core.config import settings

_client = Mistral(api_key=settings.MISTRAL_API_KEY)


class _AnsweredQuestion(BaseModel):
    question: str
    answer: str


class _QuestionAnswers(BaseModel):
    answers: list[_AnsweredQuestion]


async def embed_text(text: str) -> list[float]:
    response = await _client.embeddings.create_async(
        model=settings.MISTRAL_EMBED_MODEL,
        inputs=[text],
    )
    usage = response.usage
    print(
        f"[mistral] embed_text usage: prompt_tokens={usage.prompt_tokens} "
        f"total_tokens={usage.total_tokens}"
    )
    return response.data[0].embedding


async def answer_questions(messages: list[dict]) -> list[dict]:
    response = await _client.chat.parse_async(
        model=settings.MISTRAL_CHAT_MODEL,
        messages=messages,
        response_format=_QuestionAnswers,
    )
    usage = response.usage
    print(
        f"[mistral] answer_questions usage: prompt_tokens={usage.prompt_tokens} "
        f"completion_tokens={usage.completion_tokens} "
        f"total_tokens={usage.total_tokens}"
    )
    parsed = response.choices[0].message.parsed
    if not parsed:
        return []
    return [qa.model_dump() for qa in parsed.answers]


async def stream_chat(messages: list[dict]) -> AsyncGenerator[str, None]:
    async with await _client.chat.stream_async(
        model=settings.MISTRAL_CHAT_MODEL,
        messages=messages,
    ) as stream:
        async for event in stream:
            content = event.data.choices[0].delta.content
            if isinstance(content, str) and content:
                yield content
            if event.data.usage:
                usage = event.data.usage
                print(
                    f"[mistral] stream_chat usage: prompt_tokens={usage.prompt_tokens} "
                    f"completion_tokens={usage.completion_tokens} "
                    f"total_tokens={usage.total_tokens}"
                )
