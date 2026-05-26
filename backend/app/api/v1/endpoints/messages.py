from __future__ import annotations

import json
import uuid
import re
from base64 import b64encode
from datetime import date

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.clients.openai_client import complete, complete_text, synthesize_speech, transcribe_audio
from app.ai.prompts.ari_system_prompt import ARI_SYSTEM_PROMPT, build_ari_chat_prompt
from app.api.deps import require_workspace_access
from app.core.config import settings
from app.core.database import get_db
from app.memory import JournalEntry, JournalStore
from app.memory.recall import RecallSource, build_memory_context
from app.memory.threads import ThreadStore
from app.models.usage import AiUsageLog
from app.services.duffel import FlightSearchRequest, FlightSearchResponse, search_flights
from app.services.tool_registry import get_tool
from app.tools.catalog import load_tool_catalog

router = APIRouter()

# Only these catalog entries are allowed to leave the language-model planning
# layer and become executable desktop/backend actions.
EXECUTABLE_TOOL_NAMES = {
    "open_browser_url",
    "call_phone_number",
    "search_google_contacts",
    "create_google_calendar_event",
    "list_calendars",
    "create_calendar_event",
    "list_reminder_lists",
    "create_reminder",
    "get_weather",
    "append_journal_entry",
    "read_journal_overview",
    "search_memory",
    "search_flights",
}

_FLEXIBLE_TRAVEL_MARKERS = (
    "anywhere",
    "anywhere in the world",
    "cualquier parte",
    "cualquier lugar",
    "donde sea",
    "a donde sea",
    "any destination",
    "open destination",
)
_IATA_RE = re.compile(r"^[A-Z]{3}$")

@router.get("/")
async def list_messages():
    return []


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=12000)
    thread_id: str | None = None
    use_memory: bool = True
    memory_limit: int = Field(8, ge=0, le=20)


class ChatMemoryResult(BaseModel):
    date: date
    path: str
    line_number: int
    line: str
    reason: str | None = None
    source_date: str | None = None


class ChatResponse(BaseModel):
    reply: str
    model: str
    memory_results: list[ChatMemoryResult]
    stored: bool
    stored_actions: list[str] = []
    thread_id: str | None = None


class VoiceResponse(BaseModel):
    transcript: str
    reply: str
    model: str
    stt_model: str
    tts_model: str | None = None
    audio_base64: str | None = None
    audio_content_type: str | None = None
    stored: bool
    thread_id: str | None = None


class SpeechRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=4000)


class SpeechResponse(BaseModel):
    model: str
    voice: str
    audio_base64: str
    audio_content_type: str


class RecallRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=12000)
    limit: int = Field(8, ge=1, le=20)


class RecallResponse(BaseModel):
    memory_results: list[ChatMemoryResult]
    context: str


class OrchestrateRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=12000)
    thread_id: str | None = None
    pending_action: dict | None = None
    use_memory: bool = True
    memory_limit: int = Field(8, ge=0, le=20)


class OrchestrateResponse(BaseModel):
    mode: str = "reply"
    reply: str
    tool_name: str | None = None
    params: dict = Field(default_factory=dict)
    missing: list[str] = Field(default_factory=list)
    requires_confirmation: bool = False
    confidence: float = 0.0
    language: str = "en"
    model: str
    memory_results: list[ChatMemoryResult] = []
    thread_id: str | None = None


class ThreadCreateRequest(BaseModel):
    title: str | None = Field(None, max_length=120)


class ThreadSummaryResponse(BaseModel):
    id: str
    title: str
    date: date
    path: str
    updated_at: str
    message_count: int


class ThreadResponse(BaseModel):
    id: str
    title: str
    date: date
    path: str
    created_at: str
    updated_at: str
    messages: list[ConversationMessageResponse]


class RecentMessageResponse(BaseModel):
    date: date
    line_number: int
    title: str


class ConversationMessageResponse(BaseModel):
    role: str
    content: str


class ConversationResponse(BaseModel):
    date: date
    line_number: int
    title: str
    messages: list[ConversationMessageResponse]


def get_store() -> JournalStore:
    return JournalStore(settings.MEMORY_ROOT)


def get_thread_store() -> ThreadStore:
    return ThreadStore(settings.MEMORY_ROOT)


# Recall returns the exact local memory snippets that will be injected into chat
# prompts, which makes memory behavior debuggable without calling the LLM.
@router.post("/{workspace_id}/recall", response_model=RecallResponse)
async def recall_memory(
    body: RecallRequest,
    workspace_id: uuid.UUID = Depends(require_workspace_access),
):
    context = build_memory_context(
        get_store(),
        str(workspace_id),
        body.message.strip(),
        limit=body.limit,
        current_date=date.today(),
    )
    return RecallResponse(memory_results=_memory_result_responses(context.sources), context=context.prompt)


@router.get("/{workspace_id}/threads", response_model=list[ThreadSummaryResponse])
async def list_threads(
    limit: int = 30,
    workspace_id: uuid.UUID = Depends(require_workspace_access),
):
    summaries = get_thread_store().list_threads(str(workspace_id), limit=limit)
    return [
        ThreadSummaryResponse(
            id=item.id,
            title=item.title,
            date=item.date,
            path=item.path,
            updated_at=item.updated_at.isoformat(),
            message_count=item.message_count,
        )
        for item in summaries
    ]


@router.post("/{workspace_id}/threads", response_model=ThreadResponse, status_code=201)
async def create_thread(
    body: ThreadCreateRequest,
    workspace_id: uuid.UUID = Depends(require_workspace_access),
):
    thread = get_thread_store().create_thread(str(workspace_id), title=body.title)
    return _thread_response(thread)


@router.get("/{workspace_id}/threads/{thread_id}", response_model=ThreadResponse)
async def read_thread(
    thread_id: str,
    workspace_id: uuid.UUID = Depends(require_workspace_access),
):
    try:
        thread = get_thread_store().read_thread(str(workspace_id), thread_id)
    except (FileNotFoundError, ValueError):
        raise HTTPException(status_code=404, detail="thread not found")
    return _thread_response(thread)


@router.post("/{workspace_id}/chat", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    workspace_id: uuid.UUID = Depends(require_workspace_access),
):
    if not settings.OPENAI_API_KEY.strip():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OPENAI_API_KEY is not configured. Add it to backend/.env.local and restart the backend.",
        )

    return await _run_chat_pipeline(body, workspace_id)


# Voice is a full duplex convenience endpoint: audio in, transcript + ARI reply
# out, with optional synthesized audio for clients that want playback.
@router.post("/{workspace_id}/voice", response_model=VoiceResponse)
async def voice(
    workspace_id: uuid.UUID = Depends(require_workspace_access),
    db: AsyncSession = Depends(get_db),
    audio: UploadFile = File(...),
    language: str | None = Form(None),
    tts: bool = Form(True),
    use_memory: bool = Form(True),
    memory_limit: int = Form(8),
    thread_id: str | None = Form(None),
):
    if not settings.OPENAI_API_KEY.strip():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OPENAI_API_KEY is not configured. Add it to backend/.env.local and restart the backend.",
        )

    audio_bytes = await audio.read()
    if not audio_bytes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Voice request did not include audio.")
    if len(audio_bytes) > settings.VOICE_MAX_AUDIO_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Audio exceeds the {settings.VOICE_MAX_AUDIO_BYTES} byte voice limit.",
        )

    try:
        transcript = await transcribe_audio(
            audio_bytes,
            filename=audio.filename or "voice.webm",
            content_type=audio.content_type or "audio/webm",
            language=language,
        )
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"OpenAI STT failed: {exc}") from exc

    await _log_ai_usage(
        db,
        workspace_id=workspace_id,
        operation="stt",
        model=settings.VOICE_STT_MODEL,
        input_units=len(audio_bytes),
        usage_metadata={"content_type": audio.content_type, "audio_stored": False},
    )

    if not transcript:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="No speech was transcribed.")

    chat_response = await _run_chat_pipeline(
        ChatRequest(
            message=transcript,
            thread_id=thread_id,
            use_memory=use_memory,
            memory_limit=max(0, min(memory_limit, 20)),
        ),
        workspace_id,
    )

    audio_base64 = None
    audio_content_type = None
    if tts:
        try:
            spoken_audio = await synthesize_speech(chat_response.reply[:4000])
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"OpenAI TTS failed: {exc}") from exc
        await _log_ai_usage(
            db,
            workspace_id=workspace_id,
            operation="tts",
            model=settings.VOICE_TTS_MODEL,
            input_units=len(chat_response.reply),
            output_units=len(spoken_audio),
            usage_metadata={"format": settings.VOICE_TTS_RESPONSE_FORMAT, "audio_stored": False},
        )
        audio_base64 = b64encode(spoken_audio).decode("ascii")
        audio_content_type = _audio_content_type(settings.VOICE_TTS_RESPONSE_FORMAT)

    return VoiceResponse(
        transcript=transcript,
        reply=chat_response.reply,
        model=chat_response.model,
        stt_model=settings.VOICE_STT_MODEL,
        tts_model=settings.VOICE_TTS_MODEL if tts else None,
        audio_base64=audio_base64,
        audio_content_type=audio_content_type,
        stored=chat_response.stored,
        thread_id=chat_response.thread_id,
    )


@router.post("/{workspace_id}/speech", response_model=SpeechResponse)
async def speech(
    body: SpeechRequest,
    workspace_id: uuid.UUID = Depends(require_workspace_access),
    db: AsyncSession = Depends(get_db),
):
    if not settings.OPENAI_API_KEY.strip():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OPENAI_API_KEY is not configured. Add it to backend/.env.local and restart the backend.",
        )

    text = body.text.strip()
    try:
        spoken_audio = await synthesize_speech(text)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"OpenAI TTS failed: {exc}") from exc

    await _log_ai_usage(
        db,
        workspace_id=workspace_id,
        operation="tts",
        model=settings.VOICE_TTS_MODEL,
        input_units=len(text),
        output_units=len(spoken_audio),
        usage_metadata={"format": settings.VOICE_TTS_RESPONSE_FORMAT, "audio_stored": False},
    )

    return SpeechResponse(
        model=settings.VOICE_TTS_MODEL,
        voice=settings.VOICE_TTS_VOICE,
        audio_base64=b64encode(spoken_audio).decode("ascii"),
        audio_content_type=_audio_content_type(settings.VOICE_TTS_RESPONSE_FORMAT),
    )


async def _run_chat_pipeline(body: ChatRequest, workspace_id: uuid.UUID) -> ChatResponse:
    user_message = body.message.strip()
    store = get_store()
    thread_store = get_thread_store()
    thread_id = _ensure_thread(thread_store, str(workspace_id), body.thread_id, user_message)

    # The final prompt is built from three layers: targeted memory recall,
    # recent conversation context, and the current executable tool catalog.
    memory_results = []
    memory_context = ""
    if body.use_memory and body.memory_limit > 0:
        recall = build_memory_context(
            store,
            str(workspace_id),
            user_message,
            limit=body.memory_limit,
            current_date=date.today(),
        )
        memory_results = recall.sources
        memory_context = recall.prompt
    recent_context = (
        thread_store.context(str(workspace_id), thread_id, limit=8)
        if thread_id
        else _recent_chat_context(store, str(workspace_id), limit=8)
    )

    tool_reply = await _maybe_run_chat_tool(user_message, recent_context, memory_context, memory_results)
    if tool_reply is not None:
        if thread_id:
            thread_store.append_message(str(workspace_id), thread_id, "user", user_message, title_hint=user_message)
            thread_store.append_message(str(workspace_id), thread_id, "assistant", tool_reply)
        else:
            store.append_entry(
                str(workspace_id),
                date.today(),
                JournalEntry(section="chat", text=f"User: {user_message}"),
            )
            store.append_entry(
                str(workspace_id),
                date.today(),
                JournalEntry(section="chat", text=f"ARI: {tool_reply}"),
            )
        stored_actions = _store_detected_actions(store, str(workspace_id), user_message)
        return ChatResponse(
            reply=tool_reply,
            model=settings.AI_MODEL,
            memory_results=_memory_result_responses(memory_results),
            stored=True,
            stored_actions=stored_actions,
            thread_id=thread_id,
        )

    prompt = build_ari_chat_prompt(
        user_message,
        memory_context,
        recent_context,
        current_date=date.today().isoformat(),
        available_tools=_tool_catalog_context(),
    )

    try:
        reply = await complete_text(prompt, system_prompt=ARI_SYSTEM_PROMPT)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"OpenAI request failed: {exc}",
        ) from exc

    if thread_id:
        thread_store.append_message(str(workspace_id), thread_id, "user", user_message, title_hint=user_message)
        thread_store.append_message(str(workspace_id), thread_id, "assistant", reply)
    else:
        store.append_entry(
            str(workspace_id),
            date.today(),
            JournalEntry(section="chat", text=f"User: {user_message}"),
        )
        store.append_entry(
            str(workspace_id),
            date.today(),
            JournalEntry(section="chat", text=f"ARI: {reply}"),
        )
    stored_actions = _store_detected_actions(store, str(workspace_id), user_message)

    return ChatResponse(
        reply=reply,
        model=settings.AI_MODEL,
        memory_results=_memory_result_responses(memory_results),
        stored=True,
        stored_actions=stored_actions,
        thread_id=thread_id,
    )


async def _maybe_run_chat_tool(
    user_message: str,
    recent_context: str,
    memory_context: str,
    memory_results: list[RecallSource],
) -> str | None:
    if not _should_try_tool_orchestration(user_message, recent_context):
        return None

    prompt = _build_orchestrator_prompt(
        user_message,
        pending_action=None,
        memory_context=memory_context,
        recent_context=recent_context,
    )
    try:
        raw = await complete(prompt, system_prompt=_ARI_ORCHESTRATOR_SYSTEM_PROMPT)
        response = _normalize_orchestration(json.loads(raw), memory_results)
    except Exception:
        return None

    if response.tool_name != "search_flights":
        return None
    if response.mode == "ask":
        return response.reply
    if response.mode != "tool_ready":
        return None

    try:
        search_request = FlightSearchRequest(**response.params)
    except Exception as exc:
        return f"No pude iniciar la búsqueda de vuelos porque faltan datos válidos: {exc}"

    try:
        results = await search_flights(search_request)
    except HTTPException as exc:
        return _format_flight_search_error(search_request, exc)
    except Exception as exc:
        return (
            "Intenté buscar vuelos, pero la conexión con el proveedor falló. "
            f"Detalle técnico: {exc}"
        )
    return _format_flight_search_results(search_request, results)


def _should_try_tool_orchestration(user_message: str, recent_context: str) -> bool:
    text = f"{user_message}\n{recent_context}".lower()
    return any(
        marker in text
        for marker in (
            "vuelo",
            "vuelos",
            "flight",
            "flights",
            "aeropuerto",
            "airport",
            "origen",
            "destino",
            "ida",
            "vuelta",
            "resultados",
        )
    )


def _format_flight_search_error(body: FlightSearchRequest, exc: HTTPException) -> str:
    detail = str(exc.detail or "error desconocido")
    if exc.status_code == status.HTTP_503_SERVICE_UNAVAILABLE:
        return (
            f"No puedo buscar vuelos {body.origin} -> {body.destination} para "
            f"{body.departure_date.isoformat()} porque el proveedor de vuelos no está configurado. "
            f"Detalle: {detail}"
        )
    return (
        f"Intenté buscar vuelos {body.origin} -> {body.destination} para "
        f"{body.departure_date.isoformat()}, pero el proveedor devolvió un error. "
        f"Detalle: {detail}"
    )


def _format_flight_search_results(body: FlightSearchRequest, results: FlightSearchResponse) -> str:
    route = f"{body.origin} -> {body.destination}"
    if not results.results:
        return (
            f"He buscado vuelos {route} para {body.departure_date.isoformat()}, "
            "pero el proveedor no devolvió ofertas disponibles para esos criterios."
        )

    lines = [
        f"Encontré {len(results.results)} opción(es) de vuelo {route} para {body.departure_date.isoformat()}:"
    ]
    for index, offer in enumerate(results.results, start=1):
        first_slice = offer.slices[0] if offer.slices else []
        first_segment = first_slice[0] if first_slice else None
        last_segment = first_slice[-1] if first_slice else None
        carrier = first_segment.marketing_carrier if first_segment else None
        flight = first_segment.flight_number if first_segment else None
        departs = _format_flight_time(first_segment.departing_at if first_segment else None)
        arrives = _format_flight_time(last_segment.arriving_at if last_segment else None)
        stops = max(0, len(first_slice) - 1)
        stops_text = "directo" if stops == 0 else f"{stops} escala(s)"
        carrier_text = f"{carrier} {flight or ''}".strip() if carrier else "aerolínea no indicada"
        lines.append(
            f"{index}. {offer.total_amount} {offer.total_currency} - "
            f"{carrier_text} - salida {departs}, llegada {arrives} - {stops_text}."
        )
    if results.raw_result_count > len(results.results):
        lines.append(f"Hay {results.raw_result_count} ofertas en total; te muestro las más baratas.")
    return "\n".join(lines)


def _format_flight_time(value: str | None) -> str:
    if not value:
        return "hora no indicada"
    return value.replace("T", " ")[:16]


# Orchestration asks the model for structured intent, then normalizes the result
# against the local tool catalog before any client is allowed to execute it.
@router.post("/{workspace_id}/orchestrate", response_model=OrchestrateResponse)
async def orchestrate(
    body: OrchestrateRequest,
    workspace_id: uuid.UUID = Depends(require_workspace_access),
):
    if not settings.OPENAI_API_KEY.strip():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OPENAI_API_KEY is not configured. Add it to backend/.env.local and restart the backend.",
        )

    user_message = body.message.strip()
    store = get_store()
    thread_store = get_thread_store()
    thread_id = _ensure_thread(thread_store, str(workspace_id), body.thread_id, user_message)
    memory_results = []
    memory_context = ""
    if body.use_memory and body.memory_limit > 0:
        recall = build_memory_context(
            store,
            str(workspace_id),
            user_message,
            limit=body.memory_limit,
            current_date=date.today(),
        )
        memory_results = recall.sources
        memory_context = recall.prompt
    recent_context = (
        thread_store.context(str(workspace_id), thread_id, limit=8)
        if thread_id
        else _recent_chat_context(store, str(workspace_id), limit=8)
    )
    prompt = _build_orchestrator_prompt(
        user_message,
        body.pending_action,
        memory_context,
        recent_context,
    )

    try:
        raw = await complete(prompt, system_prompt=_ARI_ORCHESTRATOR_SYSTEM_PROMPT)
        data = json.loads(raw)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"ARI orchestration failed: {exc}",
        ) from exc

    response = _normalize_orchestration(data, memory_results)
    response.thread_id = thread_id

    if thread_id:
        thread_store.append_message(str(workspace_id), thread_id, "user", user_message, title_hint=user_message)
        thread_store.append_message(str(workspace_id), thread_id, "assistant", response.reply)
    else:
        store.append_entry(
            str(workspace_id),
            date.today(),
            JournalEntry(section="chat", text=f"User: {user_message}"),
        )
        store.append_entry(
            str(workspace_id),
            date.today(),
            JournalEntry(section="chat", text=f"ARI: {response.reply}"),
        )
    _store_detected_actions(store, str(workspace_id), user_message)
    return response


@router.get("/{workspace_id}/recent", response_model=list[RecentMessageResponse])
async def recent_messages(
    limit: int = 20,
    workspace_id: uuid.UUID = Depends(require_workspace_access),
):
    bounded_limit = max(1, min(limit, 50))
    results = get_store().search(str(workspace_id), "User:", limit=100)
    recent = []
    for item in reversed(results):
        _, _, title = item.line.partition("User:")
        title = title.strip()
        if not title:
            continue
        recent.append(
            RecentMessageResponse(
                date=item.date,
                line_number=item.line_number,
                title=title[:120],
            )
        )
        if len(recent) >= bounded_limit:
            break
    return recent


@router.get("/{workspace_id}/conversation/{day}/{line_number}", response_model=ConversationResponse)
async def read_conversation(
    day: date,
    line_number: int,
    workspace_id: uuid.UUID = Depends(require_workspace_access),
):
    if line_number < 1:
        raise HTTPException(status_code=400, detail="line_number must be positive")

    content = get_store().read_day(str(workspace_id), day)
    lines = content.splitlines()
    index = line_number - 1
    if index >= len(lines):
        raise HTTPException(status_code=404, detail="conversation not found")

    user_text = _extract_chat_content(lines[index], "User:")
    if user_text is None:
        raise HTTPException(status_code=404, detail="conversation not found")

    messages = [ConversationMessageResponse(role="user", content=user_text)]
    for follow_line in lines[index + 1 :]:
        if _extract_chat_content(follow_line, "User:") is not None:
            break
        ari_text = _extract_chat_content(follow_line, "ARI:")
        if ari_text is not None:
            messages.append(ConversationMessageResponse(role="assistant", content=ari_text))
            break

    return ConversationResponse(
        date=day,
        line_number=line_number,
        title=user_text[:120],
        messages=messages,
    )


def _extract_chat_content(line: str, marker: str) -> str | None:
    _, found, content = line.partition(marker)
    if not found:
        return None
    return content.strip()


def _ensure_thread(thread_store: ThreadStore, workspace_id: str, thread_id: str | None, title_hint: str) -> str | None:
    # A missing thread id means legacy journal mode. A supplied id must already
    # exist so clients cannot accidentally create shadow conversations.
    if thread_id:
        try:
            thread_store.read_thread(workspace_id, thread_id)
        except (FileNotFoundError, ValueError):
            raise HTTPException(status_code=404, detail="thread not found")
        return thread_id
    return None


def _thread_response(thread) -> ThreadResponse:
    return ThreadResponse(
        id=thread.id,
        title=thread.title,
        date=thread.date,
        path=thread.path,
        created_at=thread.created_at.isoformat(),
        updated_at=thread.updated_at.isoformat(),
        messages=[
            ConversationMessageResponse(role=message.role, content=message.content)
            for message in thread.messages
        ],
    )


def _memory_result_responses(sources: list[RecallSource]) -> list[ChatMemoryResult]:
    return [
        ChatMemoryResult(
            date=source.date,
            path=source.path,
            line_number=source.line_number,
            line=source.line,
            reason=source.reason,
            source_date=source.source_date,
        )
        for source in sources
    ]


def _recent_chat_context(store: JournalStore, workspace_id: str, limit: int = 8) -> str:
    overview = store.overview(workspace_id, date.today())
    chat_lines = overview.sections.get("chat", [])
    recent = chat_lines[-limit:]
    cleaned = []
    for line in recent:
        _, _, content = line.partition(" ")
        cleaned.append(content.strip() if content else line.strip())
    return "\n".join(cleaned)


def _audio_content_type(response_format: str) -> str:
    return {
        "mp3": "audio/mpeg",
        "wav": "audio/wav",
        "opus": "audio/ogg",
        "aac": "audio/aac",
        "flac": "audio/flac",
        "pcm": "audio/L16",
    }.get(response_format, f"audio/{response_format}")


async def _log_ai_usage(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    operation: str,
    model: str,
    input_units: int = 0,
    output_units: int = 0,
    usage_metadata: dict | None = None,
) -> None:
    # Usage logging must never break the user-facing AI path, so failures are
    # rolled back and swallowed here after the primary operation succeeded.
    try:
        db.add(
            AiUsageLog(
                workspace_id=workspace_id,
                provider="openai",
                operation=operation,
                model=model,
                input_units=input_units,
                output_units=output_units,
                usage_metadata=usage_metadata or {},
            )
        )
        await db.commit()
    except Exception:
        await db.rollback()


def _tool_catalog_context() -> str:
    # Chat gets a readable catalog; orchestration gets stricter JSON below.
    executable_lines = []
    planned_lines = []
    for tool in load_tool_catalog():
        required = ", ".join(tool.get("schema", {}).get("required", [])) or "none"
        confirmation = "confirmation required" if tool.get("requires_confirmation") else "no confirmation"
        line = (
            f"- {tool['name']} ({tool['scope']}, {tool.get('risk_level', 'low')}, {confirmation}; required: {required})"
        )
        if tool.get("name") in EXECUTABLE_TOOL_NAMES:
            executable_lines.append(line)
        else:
            planned_lines.append(f"{line} [planned/non-executable]")
    return "\n".join(
        [
            "Executable tools:",
            *(executable_lines or ["- none"]),
            "",
            "Planned/non-executable tools:",
            *(planned_lines or ["- none"]),
        ]
    )


_ARI_ORCHESTRATOR_SYSTEM_PROMPT = """
You are ARI Solara's execution brain.
Return only valid JSON. Do not include markdown.

You decide whether ARI should:
- reply: normal conversation, thinking, advice, drafting, explanation, emotional support, brainstorming.
- ask: a short clarifying question because execution needs a missing detail.
- tool_confirmation: a tool can be prepared and needs user confirmation before local execution.
- tool_ready: a no-confirmation tool can run now.

Use the tool catalog exactly. Never invent tool names, calendar names, files, external results, prices or locations.
For memory recall, use only the provided local memory snippets and cite the journal date or file:line reference.
If the snippets are empty or insufficient for a memory question, say that memory is not enough instead of inventing.
Only tools listed under executable tools can be prepared for execution.
If the user asks for a non-executable/planned tool, explain that real execution is not connected yet; do not say you are searching or that results exist.
If a user asks "how are you?" or asks to think through something, mode is reply.
If the user asks for an available tool, extract params from natural language and pending action context.
If a required field is missing, mode is ask and missing lists only those fields.
If all required fields are present and the tool requires confirmation, mode is tool_confirmation.
If all required fields are present and the tool does not require confirmation, mode is tool_ready.
For search_flights, Duffel requires fixed IATA airport or city codes for both origin and destination.
Convert clear city/airport names to IATA codes when unambiguous, such as Barcelona -> BCN, Lisbon/Lisboa -> LIS, Berlin -> BER, Tokyo -> NRT or TYO when the user is flexible.
If the user says "anywhere", "cualquier parte", "anywhere in the world", or leaves origin/destination flexible, ask for one fixed origin and one fixed destination before searching.
For map or directions requests, prepare open_browser_url when the place or route is clear:
- Place/search URL: https://www.google.com/maps/search/?api=1&query={url_encoded_query}
- Route URL: https://www.google.com/maps/dir/?api=1&origin={url_encoded_origin}&destination={url_encoded_destination}
Do not ask the user to provide the map URL if you can construct it from their request.
For calendar events without duration, assume 30 minutes.
For relative dates, use the provided current date.
For short follow-ups, merge with pending_action instead of starting over.
Speak in the user's language unless they requested another language.

JSON shape:
{
  "mode": "reply" | "ask" | "tool_confirmation" | "tool_ready",
  "reply": "what ARI should say to the user",
  "tool_name": string | null,
  "params": object,
  "missing": string[],
  "requires_confirmation": boolean,
  "confidence": number,
  "language": "en" | "es" | "ru" | "uk" | "it" | "fr" | "de" | "pt"
}
""".strip()


def _build_orchestrator_prompt(
    message: str,
    pending_action: dict | None,
    memory_context: str,
    recent_context: str,
) -> str:
    return f"""
Current date: {date.today().isoformat()}

Available tool catalog:
{json.dumps(_executable_tool_catalog(), ensure_ascii=False, indent=2)}

Planned but not executable yet:
{json.dumps(_planned_tool_names(), ensure_ascii=False)}

Pending action:
{json.dumps(pending_action or None, ensure_ascii=False)}

Recent conversation:
{recent_context or "(none)"}

Local memory snippets:
{memory_context or "(none)"}

User message:
{message}
""".strip()


def _normalize_orchestration(data: dict, memory_results: list[RecallSource]) -> OrchestrateResponse:
    # Treat model output as untrusted: clamp modes/confidence, validate tool
    # names, recompute missing fields, and downgrade impossible executions.
    mode = str(data.get("mode") or "reply")
    if mode not in {"reply", "ask", "tool_confirmation", "tool_ready"}:
        mode = "reply"
    tool_name = data.get("tool_name")
    tool = get_tool(tool_name) if tool_name else None
    if tool_name and tool_name not in EXECUTABLE_TOOL_NAMES:
        reply = str(data.get("reply") or "").strip()
        if _looks_like_fake_execution_reply(reply):
            reply = (
                "Todavía no tengo una búsqueda real de vuelos/hoteles conectada. "
                "Puedo ayudarte a preparar origen, destino, fechas, presupuesto y preferencias, "
                "pero no debo decir que busqué resultados hasta conectar un proveedor real."
            )
        return OrchestrateResponse(
            mode="reply",
            reply=reply or "Esa herramienta todavía no está conectada para ejecución real.",
            tool_name=None,
            params={},
            missing=[],
            requires_confirmation=False,
            confidence=max(0.0, min(1.0, float(data.get("confidence") or 0))),
            language=str(data.get("language") or "es"),
            model=settings.AI_MODEL,
            memory_results=_memory_result_responses(memory_results),
        )
    params = data.get("params") if isinstance(data.get("params"), dict) else {}
    missing: list[str] = []
    requires_confirmation = False
    if tool:
        required = tool.get("schema", {}).get("required", [])
        missing = [key for key in required if params.get(key) in (None, "")]
        model_missing = data.get("missing") if isinstance(data.get("missing"), list) else []
        for key in model_missing:
            if isinstance(key, str) and key not in missing:
                missing.append(key)
        if tool_name == "search_flights":
            missing = _flight_search_missing_fields(params, missing)
        requires_confirmation = bool(tool.get("requires_confirmation", False))
        if missing:
            mode = "ask"
        elif requires_confirmation and mode == "tool_ready":
            mode = "tool_confirmation"
        elif not requires_confirmation and mode == "tool_confirmation":
            mode = "tool_ready"
    else:
        tool_name = None
        params = {}
        missing = []
        requires_confirmation = False
        if mode in {"tool_confirmation", "tool_ready"}:
            mode = "reply"
    reply = str(data.get("reply") or "").strip()
    if tool_name == "search_flights" and mode == "ask" and missing:
        reply = _flight_search_clarifying_reply(missing, str(data.get("language") or "es"))
    if not reply:
        reply = "I need one more detail." if mode == "ask" else "I can do that."
    return OrchestrateResponse(
        mode=mode,
        reply=reply,
        tool_name=tool_name,
        params=params,
        missing=missing,
        requires_confirmation=requires_confirmation,
        confidence=max(0.0, min(1.0, float(data.get("confidence") or 0))),
        language=str(data.get("language") or "en"),
        model=settings.AI_MODEL,
        memory_results=_memory_result_responses(memory_results),
    )


def _flight_search_missing_fields(params: dict, missing: list[str]) -> list[str]:
    # Duffel needs fixed IATA-style endpoints; flexible destinations are useful
    # conversation, but not executable search parameters.
    normalized_missing = list(missing)
    for field in ("origin", "destination"):
        value = str(params.get(field) or "").strip()
        lower = value.lower()
        is_flexible = any(marker in lower for marker in _FLEXIBLE_TRAVEL_MARKERS)
        is_iata = bool(_IATA_RE.match(value.upper()))
        if (not value or is_flexible or not is_iata) and field not in normalized_missing:
            normalized_missing.append(field)
    return normalized_missing


def _flight_search_clarifying_reply(missing: list[str], language: str) -> str:
    wants_spanish = str(language or "").lower().startswith("es")
    fields = {field for field in missing if field in {"origin", "destination"}}
    if wants_spanish:
        if fields == {"origin", "destination"}:
            return "Necesito un origen y un destino concretos para buscar vuelos dentro de ARI."
        if "origin" in fields:
            return "Necesito un origen concreto, ciudad o aeropuerto, para buscar vuelos dentro de ARI."
        if "destination" in fields:
            return "Necesito un destino concreto, ciudad o aeropuerto, para buscar vuelos dentro de ARI."
        return "Necesito un detalle más para buscar vuelos dentro de ARI."
    if fields == {"origin", "destination"}:
        return "I need a fixed origin and destination to search flights inside ARI."
    if "origin" in fields:
        return "I need a fixed origin, city or airport, to search flights inside ARI."
    if "destination" in fields:
        return "I need a fixed destination, city or airport, to search flights inside ARI."
    return "I need one more detail to search flights inside ARI."


def _executable_tool_catalog() -> list[dict]:
    return [tool for tool in load_tool_catalog() if tool.get("name") in EXECUTABLE_TOOL_NAMES]


def _planned_tool_names() -> list[str]:
    return [tool["name"] for tool in load_tool_catalog() if tool.get("name") not in EXECUTABLE_TOOL_NAMES]


def _looks_like_fake_execution_reply(reply: str) -> bool:
    return any(
        marker in reply.lower()
        for marker in (
            "buscando",
            "voy a buscar",
            "searching",
            "i will search",
            "i'm searching",
            "looking for",
        )
    )


def _store_detected_actions(store: JournalStore, workspace_id: str, user_message: str) -> list[str]:
    # Lightweight capture of durable facts/tasks/decisions from normal chat.
    # This is deliberately heuristic and separate from tool orchestration.
    entries = _detect_action_entries(user_message)
    stored = []
    for section, text in entries:
        store.append_entry(workspace_id, date.today(), JournalEntry(section=section, text=text))
        stored.append(section)
    return stored


def _detect_action_entries(user_message: str) -> list[tuple[str, str]]:
    text = " ".join(user_message.strip().split())
    lower = text.lower()
    entries: list[tuple[str, str]] = []

    fact_markers = (
        "remember that ",
        "remember: ",
        "recuerda que ",
        "ten en cuenta que ",
        "my preference is ",
        "i prefer ",
        "prefiero ",
    )
    if any(marker in lower for marker in fact_markers):
        entries.append(("facts", _clip_entry(f"User memory: {text}")))

    task_markers = (
        "remind me to ",
        "recuérdame ",
        "recuerdame ",
        "i need to ",
        "need to ",
        "tengo que ",
        "hay que ",
        "todo: ",
    )
    followup_markers = (
        "follow up",
        "seguimiento",
        "call ",
        "llamar ",
        "contact ",
        "contactar ",
        "send email",
        "enviar email",
        "mandar email",
    )
    if any(marker in lower for marker in task_markers + followup_markers):
        entries.append(("pending", _clip_entry(f"Follow-up/task: {text}")))

    decision_markers = (
        "we decided ",
        "i decided ",
        "decision: ",
        "decidimos ",
        "decidí ",
        "decidi ",
    )
    if any(marker in lower for marker in decision_markers):
        entries.append(("decisions", _clip_entry(f"Decision: {text}")))

    return entries


def _clip_entry(text: str, limit: int = 500) -> str:
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"
