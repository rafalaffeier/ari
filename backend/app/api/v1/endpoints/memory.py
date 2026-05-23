from __future__ import annotations

from datetime import date, datetime

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.api.deps import require_workspace_access
from app.core.config import settings
from app.memory import JournalEntry, JournalStore


router = APIRouter()


class JournalEntryCreate(BaseModel):
    section: str = Field(..., examples=["tasks"])
    text: str = Field(..., min_length=1)
    timestamp: datetime | None = None


class JournalEntryResponse(BaseModel):
    workspace_id: str
    date: date
    path: str


class JournalDayResponse(BaseModel):
    workspace_id: str
    date: date
    content: str


class JournalOverviewResponse(BaseModel):
    workspace_id: str
    date: date
    sections: dict[str, list[str]]


class SearchResultResponse(BaseModel):
    date: date
    path: str
    line_number: int
    line: str


class TimelineDayResponse(BaseModel):
    date: date
    path: str
    entry_count: int
    sections: dict[str, int]


def get_store() -> JournalStore:
    return JournalStore(settings.MEMORY_ROOT)


@router.post("/{workspace_id}/journal/{day}/entries", response_model=JournalEntryResponse, status_code=201)
async def append_journal_entry(
    body: JournalEntryCreate,
    day: date,
    workspace_id: uuid.UUID = Depends(require_workspace_access),
):
    try:
        path = get_store().append_entry(
            str(workspace_id),
            day,
            JournalEntry(section=body.section, text=body.text, timestamp=body.timestamp),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JournalEntryResponse(workspace_id=str(workspace_id), date=day, path=str(path))


@router.get("/{workspace_id}/journal/today", response_model=JournalDayResponse)
async def read_today(workspace_id: uuid.UUID = Depends(require_workspace_access)):
    today = date.today()
    return await read_journal_day(day=today, workspace_id=workspace_id)


@router.get("/{workspace_id}/timeline", response_model=list[TimelineDayResponse])
async def read_timeline(
    limit: int = Query(30, ge=1, le=100),
    workspace_id: uuid.UUID = Depends(require_workspace_access),
):
    try:
        return get_store().timeline(str(workspace_id), limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{workspace_id}/journal/{day}/overview", response_model=JournalOverviewResponse)
async def read_journal_overview(day: date, workspace_id: uuid.UUID = Depends(require_workspace_access)):
    try:
        overview = get_store().overview(str(workspace_id), day)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JournalOverviewResponse(workspace_id=str(workspace_id), date=overview.date, sections=overview.sections)


@router.get("/{workspace_id}/journal/{day}", response_model=JournalDayResponse)
async def read_journal_day(day: date, workspace_id: uuid.UUID = Depends(require_workspace_access)):
    try:
        content = get_store().read_day(str(workspace_id), day)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JournalDayResponse(workspace_id=str(workspace_id), date=day, content=content)


@router.get("/{workspace_id}/search", response_model=list[SearchResultResponse])
async def search_memory(
    q: str = Query(..., min_length=1),
    limit: int = Query(20, ge=1, le=100),
    workspace_id: uuid.UUID = Depends(require_workspace_access),
):
    try:
        return get_store().search(str(workspace_id), q, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
