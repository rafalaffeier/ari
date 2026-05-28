from __future__ import annotations

import base64
from email.utils import parsedate_to_datetime

import httpx
from pydantic import BaseModel, Field


GOOGLE_GMAIL_READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
GOOGLE_GMAIL_MESSAGES_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages"
GOOGLE_GMAIL_THREADS_URL = "https://gmail.googleapis.com/gmail/v1/users/me/threads"


class GmailMessageSummary(BaseModel):
    id: str
    threadId: str
    snippet: str | None = None
    subject: str | None = None
    from_email: str | None = None
    to: str | None = None
    date: str | None = None
    internalDate: str | None = None
    labelIds: list[str] = Field(default_factory=list)


class GmailSearchResponse(BaseModel):
    messages: list[GmailMessageSummary]
    nextPageToken: str | None = None
    resultSizeEstimate: int | None = None


class GmailThreadMessage(BaseModel):
    id: str
    threadId: str
    snippet: str | None = None
    subject: str | None = None
    from_email: str | None = None
    to: str | None = None
    date: str | None = None
    text: str | None = None


class GmailThreadResponse(BaseModel):
    id: str
    messages: list[GmailThreadMessage]


async def search_gmail_messages_with_token(
    access_token: str,
    query: str | None,
    max_results: int = 10,
    page_token: str | None = None,
) -> GmailSearchResponse:
    params = {
        "maxResults": max(1, min(max_results, 20)),
    }
    if query:
        params["q"] = query.strip()
    if page_token:
        params["pageToken"] = page_token

    async with httpx.AsyncClient(timeout=12.0) as client:
        list_response = await client.get(
            GOOGLE_GMAIL_MESSAGES_URL,
            params=params,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if list_response.status_code >= 400:
            list_response.raise_for_status()
        payload = list_response.json()
        summaries = []
        for item in payload.get("messages", [])[: params["maxResults"]]:
            message_id = item.get("id")
            if not message_id:
                continue
            detail_response = await client.get(
                f"{GOOGLE_GMAIL_MESSAGES_URL}/{message_id}",
                params={
                    "format": "metadata",
                    "metadataHeaders": ["From", "To", "Subject", "Date"],
                    "fields": "id,threadId,labelIds,snippet,internalDate,payload(headers)",
                },
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if detail_response.status_code >= 400:
                detail_response.raise_for_status()
            summaries.append(_summary_from_message_payload(detail_response.json()))

    return GmailSearchResponse(
        messages=summaries,
        nextPageToken=payload.get("nextPageToken"),
        resultSizeEstimate=payload.get("resultSizeEstimate"),
    )


async def read_gmail_thread_with_token(
    access_token: str,
    thread_id: str,
    max_chars_per_message: int = 2400,
) -> GmailThreadResponse:
    async with httpx.AsyncClient(timeout=12.0) as client:
        response = await client.get(
            f"{GOOGLE_GMAIL_THREADS_URL}/{thread_id}",
            params={"format": "full"},
            headers={"Authorization": f"Bearer {access_token}"},
        )
    if response.status_code >= 400:
        response.raise_for_status()

    payload = response.json()
    messages = []
    for item in payload.get("messages", []):
        summary = _summary_from_message_payload(item)
        text = _extract_plain_text(item.get("payload") or "").strip()
        if max_chars_per_message > 0 and len(text) > max_chars_per_message:
            text = text[:max_chars_per_message].rstrip() + "..."
        messages.append(
            GmailThreadMessage(
                id=summary.id,
                threadId=summary.threadId,
                snippet=summary.snippet,
                subject=summary.subject,
                from_email=summary.from_email,
                to=summary.to,
                date=summary.date,
                text=text or summary.snippet,
            )
        )
    return GmailThreadResponse(id=str(payload.get("id") or thread_id), messages=messages)


def _summary_from_message_payload(item: dict) -> GmailMessageSummary:
    headers = _headers_dict((item.get("payload") or {}).get("headers") or [])
    return GmailMessageSummary(
        id=str(item.get("id") or ""),
        threadId=str(item.get("threadId") or ""),
        snippet=item.get("snippet"),
        subject=headers.get("subject"),
        from_email=headers.get("from"),
        to=headers.get("to"),
        date=_normalize_email_date(headers.get("date")),
        internalDate=item.get("internalDate"),
        labelIds=[str(label) for label in item.get("labelIds") or []],
    )


def _headers_dict(headers: list[dict]) -> dict[str, str]:
    result = {}
    for header in headers:
        name = str(header.get("name") or "").strip().lower()
        value = str(header.get("value") or "").strip()
        if name and value:
            result[name] = value
    return result


def _normalize_email_date(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return parsedate_to_datetime(value).isoformat()
    except (TypeError, ValueError):
        return value


def _extract_plain_text(part: dict | str) -> str:
    if not isinstance(part, dict):
        return ""
    mime_type = str(part.get("mimeType") or "")
    body = part.get("body") or {}
    if mime_type == "text/plain" and body.get("data"):
        return _decode_gmail_body(body.get("data"))
    for child in part.get("parts") or []:
        text = _extract_plain_text(child)
        if text:
            return text
    if body.get("data"):
        return _decode_gmail_body(body.get("data"))
    return ""


def _decode_gmail_body(data: str) -> str:
    try:
        padded = data + "=" * (-len(data) % 4)
        return base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8", errors="replace")
    except Exception:
        return ""
