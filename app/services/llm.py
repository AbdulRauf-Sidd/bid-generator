from typing import AsyncGenerator

from openai import AsyncOpenAI
from pydantic import BaseModel

from app.core.config import settings
from app.services.mistral import answer_questions as _mistral_answer_questions
from app.services.mistral import stream_chat as _mistral_stream_chat

_openai_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY) if settings.OPENAI_API_KEY else None


class _AnsweredQuestion(BaseModel):
    question: str
    answer: str


class _QuestionAnswers(BaseModel):
    answers: list[_AnsweredQuestion]


async def _stream_chat_openai(messages: list[dict]) -> AsyncGenerator[str, None]:
    stream = await _openai_client.chat.completions.create(
        model=settings.OPENAI_CHAT_MODEL,
        messages=messages,
        stream=True,
        stream_options={"include_usage": True},
    )
    async for chunk in stream:
        if chunk.usage:
            usage = chunk.usage
            print(
                f"[openai] stream_chat usage: prompt_tokens={usage.prompt_tokens} "
                f"completion_tokens={usage.completion_tokens} "
                f"total_tokens={usage.total_tokens}"
            )
        if not chunk.choices:
            continue
        content = chunk.choices[0].delta.content
        if content:
            yield content


async def stream_chat(messages: list[dict]) -> AsyncGenerator[str, None]:
    if _openai_client is None:
        async for chunk in _mistral_stream_chat(messages):
            yield chunk
        return

    emitted = False
    try:
        async for chunk in _stream_chat_openai(messages):
            emitted = True
            yield chunk
        return
    except Exception as exc:
        print(f"[llm] OpenAI stream_chat failed, falling back to Mistral: {exc}")
        if emitted:
            # Already streamed partial content to the client on this connection;
            # restarting from Mistral would duplicate text, so just stop here.
            return

    async for chunk in _mistral_stream_chat(messages):
        yield chunk


async def answer_questions(messages: list[dict]) -> list[dict]:
    if _openai_client is not None:
        try:
            response = await _openai_client.chat.completions.parse(
                model=settings.OPENAI_CHAT_MODEL,
                messages=messages,
                response_format=_QuestionAnswers,
            )
            usage = response.usage
            print(
                f"[openai] answer_questions usage: prompt_tokens={usage.prompt_tokens} "
                f"completion_tokens={usage.completion_tokens} "
                f"total_tokens={usage.total_tokens}"
            )
            parsed = response.choices[0].message.parsed
            if not parsed:
                return []
            return [qa.model_dump() for qa in parsed.answers]
        except Exception as exc:
            print(f"[llm] OpenAI answer_questions failed, falling back to Mistral: {exc}")

    return await _mistral_answer_questions(messages)
