from __future__ import annotations

import json
from openai import AsyncOpenAI
from app.core.config import settings
from app.ai.prompts.system_prompt import SYSTEM_PROMPT

_client: AsyncOpenAI | None = None


def get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    return _client


async def complete(user_prompt: str, system_prompt: str = SYSTEM_PROMPT) -> str:
    """
    Call the OpenAI API and return the raw text content.
    Raises on API error — callers must handle.
    """
    client = get_client()
    response = await client.chat.completions.create(
        model=settings.AI_MODEL,
        messages=[
            {"role": "system",  "content": system_prompt},
            {"role": "user",    "content": user_prompt},
        ],
        temperature=0.2,          # low temp = more deterministic JSON
        response_format={"type": "json_object"},
    )
    return response.choices[0].message.content


async def complete_text(user_prompt: str, system_prompt: str = SYSTEM_PROMPT) -> str:
    """
    Call the OpenAI API for normal assistant text.
    """
    client = get_client()
    response = await client.chat.completions.create(
        model=settings.AI_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.7,
    )
    return response.choices[0].message.content or ""
