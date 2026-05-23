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


async def transcribe_audio(
    audio: bytes,
    *,
    filename: str = "voice.webm",
    content_type: str = "audio/webm",
    language: str | None = None,
) -> str:
    """
    Transcribe one push-to-talk audio payload. Audio bytes are not stored.
    """
    client = get_client()
    kwargs = {
        "model": settings.VOICE_STT_MODEL,
        "file": (filename, audio, content_type),
        "response_format": "json",
        "temperature": 0,
    }
    if language:
        kwargs["language"] = language
    transcription = await client.audio.transcriptions.create(**kwargs)
    if isinstance(transcription, str):
        return transcription.strip()
    return (getattr(transcription, "text", "") or "").strip()


async def synthesize_speech(text: str) -> bytes:
    """
    Generate TTS audio for a validated assistant response.
    """
    client = get_client()
    response = await client.audio.speech.create(
        model=settings.VOICE_TTS_MODEL,
        voice=settings.VOICE_TTS_VOICE,
        input=text,
        response_format=settings.VOICE_TTS_RESPONSE_FORMAT,
    )
    return await response.aread()
