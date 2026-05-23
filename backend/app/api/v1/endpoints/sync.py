from __future__ import annotations

import uuid
from datetime import datetime, timezone
import re
from urllib.parse import quote

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_workspace_access
from app.core.database import get_db
from app.models.device import Device
from app.models.sync import FileVersion, SyncEvent, WorkspaceKeyWrap, WorkspaceRecoveryWrap
from app.models.user import User
from app.sync_storage import checksum_sha256, get_sync_storage

router = APIRouter()


class FileVersionUpsert(BaseModel):
    path: str = Field(..., min_length=1, max_length=2000)
    checksum_sha256: str = Field(..., min_length=64, max_length=64)
    size_bytes: int = Field(..., ge=0)
    modified_at: datetime
    base_version: int | None = Field(None, ge=1)
    storage_key: str | None = Field(None, max_length=2000)


class FileVersionOut(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    path: str
    version: int
    checksum_sha256: str
    size_bytes: int
    modified_at: datetime
    storage_key: str | None
    encryption_metadata: dict | None = None
    updated_by_user_id: uuid.UUID
    created_at: datetime


class SyncEventOut(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    file_version_id: uuid.UUID | None
    user_id: uuid.UUID
    event_type: str
    path: str
    payload: dict
    created_at: datetime


class FileContentUploadOut(FileVersionOut):
    download_url: str


class WorkspaceKeyWrapIn(BaseModel):
    device_id: uuid.UUID
    key_id: str = Field(..., min_length=1, max_length=200)
    wrapping_algorithm: str = Field(..., min_length=1, max_length=100)
    wrapped_key: str = Field(..., min_length=32, max_length=10000)


class WorkspaceKeyWrapOut(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    device_id: uuid.UUID
    key_id: str
    wrapping_algorithm: str
    wrapped_key: str
    created_by_user_id: uuid.UUID
    created_at: datetime


class WorkspaceRecoveryWrapIn(BaseModel):
    key_id: str = Field(..., min_length=1, max_length=200)
    wrapping_algorithm: str = Field(..., min_length=1, max_length=100)
    wrapped_key: str = Field(..., min_length=32, max_length=10000)
    recovery_hint: str | None = Field(None, max_length=200)


class WorkspaceRecoveryWrapOut(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    key_id: str
    wrapping_algorithm: str
    wrapped_key: str
    recovery_hint: str | None
    created_by_user_id: uuid.UUID
    created_at: datetime


@router.post("/{workspace_id}/files", response_model=FileVersionOut, status_code=201)
async def upsert_file_version(
    body: FileVersionUpsert,
    workspace_id: uuid.UUID = Depends(require_workspace_access),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    path = _normalize_memory_path(body.path)
    result = await db.execute(
        select(FileVersion).where(FileVersion.workspace_id == workspace_id, FileVersion.path == path)
    )
    file_version = result.scalar_one_or_none()
    event_type = "file_version.created"

    if file_version is None:
        file_version = FileVersion(
            workspace_id=workspace_id,
            path=path,
            version=1,
            checksum_sha256=body.checksum_sha256,
            size_bytes=body.size_bytes,
            modified_at=body.modified_at,
            storage_key=body.storage_key,
            updated_by_user_id=current_user.id,
        )
        db.add(file_version)
        await db.flush()
    else:
        if body.base_version is not None and body.base_version != file_version.version:
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "File version conflict",
                    "current_version": file_version.version,
                    "current_checksum_sha256": file_version.checksum_sha256,
                },
            )
        file_version.version += 1
        file_version.checksum_sha256 = body.checksum_sha256
        file_version.size_bytes = body.size_bytes
        file_version.modified_at = body.modified_at
        file_version.storage_key = body.storage_key
        file_version.updated_by_user_id = current_user.id
        event_type = "file_version.updated"

    db.add(
        SyncEvent(
            workspace_id=workspace_id,
            file_version_id=file_version.id,
            user_id=current_user.id,
            event_type=event_type,
            path=path,
            payload={
                "version": file_version.version,
                "checksum_sha256": file_version.checksum_sha256,
                "size_bytes": file_version.size_bytes,
                "modified_at": file_version.modified_at.isoformat(),
            },
        )
    )
    await db.commit()
    await db.refresh(file_version)
    return file_version


@router.post("/{workspace_id}/keys/wraps", response_model=WorkspaceKeyWrapOut, status_code=201)
async def upsert_workspace_key_wrap(
    body: WorkspaceKeyWrapIn,
    workspace_id: uuid.UUID = Depends(require_workspace_access),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    key_id, wrapping_algorithm, wrapped_key = _validate_key_wrap_fields(
        body.key_id, body.wrapping_algorithm, body.wrapped_key
    )
    device = await _get_active_owned_device(db, workspace_id, current_user.id, body.device_id)
    result = await db.execute(
        select(WorkspaceKeyWrap).where(
            WorkspaceKeyWrap.workspace_id == workspace_id,
            WorkspaceKeyWrap.device_id == device.id,
            WorkspaceKeyWrap.key_id == key_id,
        )
    )
    wrap = result.scalar_one_or_none()
    if wrap is None:
        wrap = WorkspaceKeyWrap(
            workspace_id=workspace_id,
            device_id=device.id,
            key_id=key_id,
            wrapping_algorithm=wrapping_algorithm,
            wrapped_key=wrapped_key,
            created_by_user_id=current_user.id,
        )
        db.add(wrap)
    else:
        wrap.wrapping_algorithm = wrapping_algorithm
        wrap.wrapped_key = wrapped_key
        wrap.created_by_user_id = current_user.id
    await db.commit()
    await db.refresh(wrap)
    return wrap


@router.get("/{workspace_id}/keys/wraps", response_model=list[WorkspaceKeyWrapOut])
async def list_workspace_key_wraps(
    device_id: uuid.UUID = Query(...),
    workspace_id: uuid.UUID = Depends(require_workspace_access),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    device = await _get_active_owned_device(db, workspace_id, current_user.id, device_id)
    result = await db.execute(
        select(WorkspaceKeyWrap)
        .where(
            WorkspaceKeyWrap.workspace_id == workspace_id,
            WorkspaceKeyWrap.device_id == device.id,
        )
        .order_by(WorkspaceKeyWrap.created_at.desc())
    )
    return list(result.scalars())


@router.post("/{workspace_id}/keys/recovery", response_model=WorkspaceRecoveryWrapOut, status_code=201)
async def upsert_workspace_recovery_wrap(
    body: WorkspaceRecoveryWrapIn,
    workspace_id: uuid.UUID = Depends(require_workspace_access),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    key_id, wrapping_algorithm, wrapped_key = _validate_key_wrap_fields(
        body.key_id, body.wrapping_algorithm, body.wrapped_key
    )
    recovery_hint = _validate_recovery_hint(body.recovery_hint)
    result = await db.execute(
        select(WorkspaceRecoveryWrap).where(
            WorkspaceRecoveryWrap.workspace_id == workspace_id,
            WorkspaceRecoveryWrap.key_id == key_id,
        )
    )
    wrap = result.scalar_one_or_none()
    if wrap is None:
        wrap = WorkspaceRecoveryWrap(
            workspace_id=workspace_id,
            key_id=key_id,
            wrapping_algorithm=wrapping_algorithm,
            wrapped_key=wrapped_key,
            recovery_hint=recovery_hint,
            created_by_user_id=current_user.id,
        )
        db.add(wrap)
    else:
        wrap.wrapping_algorithm = wrapping_algorithm
        wrap.wrapped_key = wrapped_key
        wrap.recovery_hint = recovery_hint
        wrap.created_by_user_id = current_user.id
    await db.commit()
    await db.refresh(wrap)
    return wrap


@router.get("/{workspace_id}/keys/recovery", response_model=list[WorkspaceRecoveryWrapOut])
async def list_workspace_recovery_wraps(
    workspace_id: uuid.UUID = Depends(require_workspace_access),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(WorkspaceRecoveryWrap)
        .where(WorkspaceRecoveryWrap.workspace_id == workspace_id)
        .order_by(WorkspaceRecoveryWrap.created_at.desc())
    )
    return list(result.scalars())


@router.put("/{workspace_id}/files/content", response_model=FileContentUploadOut, status_code=201)
async def upload_markdown_file(
    content: bytes = Body(..., media_type="application/octet-stream"),
    path: str = Query(..., min_length=1, max_length=2000),
    base_version: int | None = Query(None, ge=1),
    modified_at: datetime | None = None,
    encryption_algorithm: str = Header(..., alias="X-Encryption-Algorithm"),
    encryption_key_id: str = Header(..., alias="X-Encryption-Key-Id"),
    encryption_nonce: str = Header(..., alias="X-Encryption-Nonce"),
    encryption_envelope_version: int = Header(1, alias="X-Encryption-Envelope-Version", ge=1),
    workspace_id: uuid.UUID = Depends(require_workspace_access),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    normalized_path = _validate_markdown_path(_normalize_memory_path(path))
    encryption_metadata = _build_encryption_metadata(
        algorithm=encryption_algorithm,
        key_id=encryption_key_id,
        nonce=encryption_nonce,
        envelope_version=encryption_envelope_version,
    )
    digest = checksum_sha256(content)
    now = modified_at or datetime.now(timezone.utc)

    result = await db.execute(
        select(FileVersion).where(FileVersion.workspace_id == workspace_id, FileVersion.path == normalized_path)
    )
    file_version = result.scalar_one_or_none()
    event_type = "file_content.created"

    if file_version is None:
        file_version = FileVersion(
            workspace_id=workspace_id,
            path=normalized_path,
            version=1,
            checksum_sha256=digest,
            size_bytes=len(content),
            modified_at=now,
            storage_key=None,
            encryption_metadata=encryption_metadata,
            updated_by_user_id=current_user.id,
        )
        db.add(file_version)
        await db.flush()
    else:
        if base_version is not None and base_version != file_version.version:
            conflict_file = await _preserve_conflict_file(
                db=db,
                storage=get_sync_storage(),
                workspace_id=workspace_id,
                current_user=current_user,
                original=file_version,
                path=normalized_path,
                content=content,
                checksum_sha256=digest,
                encryption_metadata=encryption_metadata,
                modified_at=now,
            )
            await db.commit()
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "File version conflict",
                    "current_version": file_version.version,
                    "current_checksum_sha256": file_version.checksum_sha256,
                    "conflict_path": conflict_file.path,
                    "conflict_version": conflict_file.version,
                    "conflict_checksum_sha256": conflict_file.checksum_sha256,
                },
            )
        file_version.version += 1
        file_version.checksum_sha256 = digest
        file_version.size_bytes = len(content)
        file_version.modified_at = now
        file_version.encryption_metadata = encryption_metadata
        file_version.updated_by_user_id = current_user.id
        event_type = "file_content.updated"

    storage = get_sync_storage()
    storage_key = storage.build_key(workspace_id, file_version.id, file_version.version, digest)
    storage.write(storage_key, content)
    file_version.storage_key = storage_key

    db.add(
        SyncEvent(
            workspace_id=workspace_id,
            file_version_id=file_version.id,
            user_id=current_user.id,
            event_type=event_type,
            path=normalized_path,
            payload={
                "version": file_version.version,
                "checksum_sha256": digest,
                "size_bytes": len(content),
                "modified_at": now.isoformat(),
                "storage_key": storage_key,
                "encryption": encryption_metadata,
            },
        )
    )
    await db.commit()
    await db.refresh(file_version)
    file_out = FileVersionOut.model_validate(file_version, from_attributes=True)
    return FileContentUploadOut(
        **file_out.model_dump(),
        download_url=f"/api/v1/sync/{workspace_id}/files/content?path={quote(normalized_path)}",
    )


@router.get("/{workspace_id}/files/content")
async def download_markdown_file(
    path: str = Query(..., min_length=1, max_length=2000),
    workspace_id: uuid.UUID = Depends(require_workspace_access),
    db: AsyncSession = Depends(get_db),
):
    normalized_path = _validate_markdown_path(_normalize_memory_path(path))
    result = await db.execute(
        select(FileVersion).where(FileVersion.workspace_id == workspace_id, FileVersion.path == normalized_path)
    )
    file_version = result.scalar_one_or_none()
    if file_version is None or not file_version.storage_key:
        raise HTTPException(status_code=404, detail="file not found")

    storage = get_sync_storage()
    if not storage.exists(file_version.storage_key):
        raise HTTPException(status_code=404, detail="file content not found")
    if not file_version.encryption_metadata:
        raise HTTPException(status_code=409, detail="file content is missing encryption metadata")

    return Response(
        content=storage.read(file_version.storage_key),
        media_type="application/octet-stream",
        headers={
            "X-File-Version": str(file_version.version),
            "X-Checksum-SHA256": file_version.checksum_sha256,
            "X-Size-Bytes": str(file_version.size_bytes),
            "X-Encryption-Algorithm": file_version.encryption_metadata["algorithm"],
            "X-Encryption-Key-Id": file_version.encryption_metadata["key_id"],
            "X-Encryption-Nonce": file_version.encryption_metadata["nonce"],
            "X-Encryption-Envelope-Version": str(file_version.encryption_metadata["envelope_version"]),
        },
    )


@router.get("/{workspace_id}/files", response_model=list[FileVersionOut])
async def list_file_versions(
    prefix: str | None = None,
    limit: int = Query(100, ge=1, le=500),
    workspace_id: uuid.UUID = Depends(require_workspace_access),
    db: AsyncSession = Depends(get_db),
):
    query = select(FileVersion).where(FileVersion.workspace_id == workspace_id)
    if prefix:
        query = query.where(FileVersion.path.startswith(_normalize_memory_path(prefix)))
    result = await db.execute(query.order_by(FileVersion.path.asc()).limit(limit))
    return list(result.scalars())


@router.get("/{workspace_id}/events", response_model=list[SyncEventOut])
async def list_sync_events(
    limit: int = Query(100, ge=1, le=500),
    workspace_id: uuid.UUID = Depends(require_workspace_access),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(SyncEvent)
        .where(SyncEvent.workspace_id == workspace_id)
        .order_by(SyncEvent.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars())


def _normalize_memory_path(path: str) -> str:
    cleaned = path.strip().replace("\\", "/")
    if not cleaned:
        raise HTTPException(status_code=400, detail="path cannot be empty")
    if cleaned.startswith("/") or ".." in cleaned.split("/"):
        raise HTTPException(status_code=400, detail="path must be workspace-relative and cannot contain parent segments")
    return "/".join(part for part in cleaned.split("/") if part)


def _validate_markdown_path(path: str) -> str:
    if not path.lower().endswith(".md"):
        raise HTTPException(status_code=400, detail="only Markdown .md files can be synced")
    if not _is_metadata_safe_memory_path(path):
        raise HTTPException(status_code=400, detail="path must use the metadata-safe memory layout")
    return path


async def _preserve_conflict_file(
    db: AsyncSession,
    storage: LocalSyncStorage,
    workspace_id: uuid.UUID,
    current_user: User,
    original: FileVersion,
    path: str,
    content: bytes,
    checksum_sha256: str,
    encryption_metadata: dict,
    modified_at: datetime,
) -> FileVersion:
    conflict_path = _conflict_path(path)
    conflict_file = FileVersion(
        workspace_id=workspace_id,
        path=conflict_path,
        version=1,
        checksum_sha256=checksum_sha256,
        size_bytes=len(content),
        modified_at=modified_at,
        storage_key=None,
        encryption_metadata=encryption_metadata,
        updated_by_user_id=current_user.id,
    )
    db.add(conflict_file)
    await db.flush()

    storage_key = storage.build_key(workspace_id, conflict_file.id, conflict_file.version, checksum_sha256)
    storage.write(storage_key, content)
    conflict_file.storage_key = storage_key
    db.add(
        SyncEvent(
            workspace_id=workspace_id,
            file_version_id=conflict_file.id,
            user_id=current_user.id,
            event_type="file_content.conflict",
            path=path,
            payload={
                "conflict_path": conflict_path,
                "current_file_version_id": str(original.id),
                "current_version": original.version,
                "current_checksum_sha256": original.checksum_sha256,
                "conflict_version": conflict_file.version,
                "conflict_checksum_sha256": checksum_sha256,
                "size_bytes": len(content),
                "modified_at": modified_at.isoformat(),
                "storage_key": storage_key,
                "encryption": encryption_metadata,
            },
        )
    )
    return conflict_file


def _conflict_path(path: str) -> str:
    suffix = uuid.uuid4().hex[:12]
    return f"{path[:-3]}.conflict-{suffix}.md"


def _build_encryption_metadata(algorithm: str, key_id: str, nonce: str, envelope_version: int) -> dict:
    algorithm = algorithm.strip().upper()
    key_id = key_id.strip()
    nonce = nonce.strip()
    supported_algorithms = {"AES-256-GCM", "XCHACHA20-POLY1305"}

    if algorithm not in supported_algorithms:
        raise HTTPException(status_code=400, detail="unsupported encryption algorithm")
    if not key_id or len(key_id) > 200 or any(char.isspace() for char in key_id):
        raise HTTPException(status_code=400, detail="invalid encryption key id")
    if len(nonce) < 12 or len(nonce) > 200 or any(char.isspace() for char in nonce):
        raise HTTPException(status_code=400, detail="invalid encryption nonce")

    return {
        "envelope_version": envelope_version,
        "algorithm": algorithm,
        "key_id": key_id,
        "nonce": nonce,
    }


async def _get_active_owned_device(
    db: AsyncSession, workspace_id: uuid.UUID, user_id: uuid.UUID, device_id: uuid.UUID
) -> Device:
    result = await db.execute(
        select(Device).where(
            Device.id == device_id,
            Device.workspace_id == workspace_id,
            Device.user_id == user_id,
        )
    )
    device = result.scalar_one_or_none()
    if device is None:
        raise HTTPException(status_code=404, detail="Device not found")
    if device.revoked_at is not None or not device.agent_token_hash:
        raise HTTPException(status_code=403, detail="Device is revoked")
    return device


def _validate_key_wrap_fields(key_id: str, wrapping_algorithm: str, wrapped_key: str) -> tuple[str, str, str]:
    key_id = key_id.strip()
    wrapping_algorithm = wrapping_algorithm.strip().upper()
    wrapped_key = wrapped_key.strip()
    supported_algorithms = {"X25519-AES-256-GCM", "RECOVERY-PHRASE-AES-256-GCM", "LOCAL-TEST-AES-256-GCM"}

    if not key_id or len(key_id) > 200 or any(char.isspace() for char in key_id):
        raise HTTPException(status_code=400, detail="invalid key id")
    if wrapping_algorithm not in supported_algorithms:
        raise HTTPException(status_code=400, detail="unsupported key wrapping algorithm")
    if len(wrapped_key) < 32 or len(wrapped_key) > 10000 or any(char.isspace() for char in wrapped_key):
        raise HTTPException(status_code=400, detail="invalid wrapped key")
    return key_id, wrapping_algorithm, wrapped_key


def _validate_recovery_hint(recovery_hint: str | None) -> str | None:
    if recovery_hint is None:
        return None
    recovery_hint = recovery_hint.strip()
    if not recovery_hint:
        return None
    if len(recovery_hint) > 200:
        raise HTTPException(status_code=400, detail="invalid recovery hint")
    forbidden_fragments = ("phrase", "seed", "password", "secret", "mnemonic", "clave", "contraseña")
    lowered = recovery_hint.lower()
    if any(fragment in lowered for fragment in forbidden_fragments):
        raise HTTPException(status_code=400, detail="recovery hint must not contain recovery secret material")
    return recovery_hint


def _is_metadata_safe_memory_path(path: str) -> bool:
    patterns = (
        r"^journal/\d{4}/\d{2}/\d{4}-\d{2}-\d{2}(\.conflict-[a-f0-9]{12})?\.md$",
        r"^summaries/\d{4}-W\d{2}(\.conflict-[a-f0-9]{12})?\.md$",
        r"^summaries/\d{4}-\d{2}(\.conflict-[a-f0-9]{12})?\.md$",
        r"^entities/(projects|people|preferences)(\.conflict-[a-f0-9]{12})?\.md$",
    )
    return any(re.fullmatch(pattern, path) for pattern in patterns)
