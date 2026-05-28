from __future__ import annotations

from pydantic import BaseModel
import httpx


GOOGLE_DRIVE_FILES_URL = "https://www.googleapis.com/drive/v3/files"
GOOGLE_DRIVE_METADATA_SCOPE = "https://www.googleapis.com/auth/drive.metadata.readonly"


class GoogleDriveFileMetadata(BaseModel):
    id: str
    name: str
    mimeType: str | None = None
    webViewLink: str | None = None
    modifiedTime: str | None = None
    owners: list[str] = []


class GoogleDriveSearchResponse(BaseModel):
    files: list[GoogleDriveFileMetadata]
    nextPageToken: str | None = None


async def search_google_drive_files_with_token(
    access_token: str,
    query: str | None,
    page_size: int = 10,
    page_token: str | None = None,
) -> GoogleDriveSearchResponse:
    params = {
        "pageSize": max(1, min(page_size, 25)),
        "fields": (
            "nextPageToken,files(id,name,mimeType,webViewLink,modifiedTime,"
            "owners(displayName,emailAddress))"
        ),
        "orderBy": "modifiedTime desc",
        "supportsAllDrives": "true",
        "includeItemsFromAllDrives": "true",
        "q": _drive_search_query(query),
    }
    if page_token:
        params["pageToken"] = page_token

    async with httpx.AsyncClient(timeout=12.0) as client:
        response = await client.get(
            GOOGLE_DRIVE_FILES_URL,
            params=params,
            headers={"Authorization": f"Bearer {access_token}"},
        )
    if response.status_code >= 400:
        response.raise_for_status()

    payload = response.json()
    return GoogleDriveSearchResponse(
        files=[_drive_file_from_payload(item) for item in payload.get("files", [])],
        nextPageToken=payload.get("nextPageToken"),
    )


def _drive_search_query(query: str | None) -> str:
    value = (query or "").strip()
    if not value:
        return "trashed = false"
    escaped = value.replace("\\", "\\\\").replace("'", "\\'")
    return f"name contains '{escaped}' and trashed = false"


def _drive_file_from_payload(item: dict) -> GoogleDriveFileMetadata:
    owners = []
    for owner in item.get("owners") or []:
        label = owner.get("displayName") or owner.get("emailAddress")
        if label:
            owners.append(label)
    return GoogleDriveFileMetadata(
        id=str(item.get("id") or ""),
        name=str(item.get("name") or "Archivo sin nombre"),
        mimeType=item.get("mimeType"),
        webViewLink=item.get("webViewLink"),
        modifiedTime=item.get("modifiedTime"),
        owners=owners,
    )
