from __future__ import annotations

import re
import secrets
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

from .paths import ensure_inside_root, validate_workspace_id


THREAD_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{7,95}$")


@dataclass(frozen=True)
class ThreadMessage:
    role: str
    content: str
    timestamp: datetime | None = None


@dataclass(frozen=True)
class ThreadSummary:
    id: str
    title: str
    date: date
    path: str
    updated_at: datetime
    message_count: int


@dataclass(frozen=True)
class Thread:
    id: str
    title: str
    date: date
    path: str
    created_at: datetime
    updated_at: datetime
    messages: list[ThreadMessage]


class ThreadStore:
    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()

    def create_thread(self, workspace_id: str, title: str | None = None, now: datetime | None = None) -> Thread:
        validate_workspace_id(workspace_id)
        stamp = now or datetime.now(timezone.utc)
        thread_id = self._new_thread_id(stamp)
        clean_title = self._normalize_title(title or "New thread")
        path = ensure_inside_root(self.root, self._thread_path(workspace_id, stamp.date(), thread_id))
        path.parent.mkdir(parents=True, exist_ok=True)
        thread = Thread(
            id=thread_id,
            title=clean_title,
            date=stamp.date(),
            path=str(path.relative_to(self.root)),
            created_at=stamp,
            updated_at=stamp,
            messages=[],
        )
        path.write_text(self._render(thread), encoding="utf-8")
        return thread

    def append_message(
        self,
        workspace_id: str,
        thread_id: str,
        role: str,
        content: str,
        title_hint: str | None = None,
        now: datetime | None = None,
    ) -> Thread:
        thread = self.read_thread(workspace_id, thread_id)
        stamp = now or datetime.now(timezone.utc)
        clean_role = self._normalize_role(role)
        clean_content = self._normalize_content(content)
        title = thread.title
        if title == "New thread" and title_hint:
            title = self._normalize_title(title_hint)
        updated = Thread(
            id=thread.id,
            title=title,
            date=thread.date,
            path=thread.path,
            created_at=thread.created_at,
            updated_at=stamp,
            messages=[*thread.messages, ThreadMessage(role=clean_role, content=clean_content, timestamp=stamp)],
        )
        path = ensure_inside_root(self.root, self.root / thread.path)
        path.write_text(self._render(updated), encoding="utf-8")
        return updated

    def read_thread(self, workspace_id: str, thread_id: str) -> Thread:
        validate_workspace_id(workspace_id)
        self._validate_thread_id(thread_id)
        for path in self._thread_root(workspace_id).glob("*/*/*/*.md"):
            if path.stem == thread_id:
                return self._parse_thread(path)
        raise FileNotFoundError("thread not found")

    def list_threads(self, workspace_id: str, limit: int = 30) -> list[ThreadSummary]:
        validate_workspace_id(workspace_id)
        root = self._thread_root(workspace_id)
        if not root.exists():
            return []
        summaries = [self._thread_summary(path) for path in root.glob("*/*/*/*.md")]
        summaries.sort(key=lambda item: item.updated_at, reverse=True)
        return summaries[: max(1, min(limit, 100))]

    def context(self, workspace_id: str, thread_id: str, limit: int = 8) -> str:
        try:
            thread = self.read_thread(workspace_id, thread_id)
        except FileNotFoundError:
            return ""
        lines = []
        for message in thread.messages[-limit:]:
            label = "User" if message.role == "user" else "ARI"
            lines.append(f"{label}: {message.content}")
        return "\n".join(lines)

    def _thread_root(self, workspace_id: str) -> Path:
        return ensure_inside_root(self.root, self.root / validate_workspace_id(workspace_id) / "threads")

    def _thread_path(self, workspace_id: str, day: date, thread_id: str) -> Path:
        return self._thread_root(workspace_id) / f"{day:%Y}" / f"{day:%m}" / f"{day:%d}" / f"{thread_id}.md"

    def _new_thread_id(self, stamp: datetime) -> str:
        return f"{stamp:%Y%m%d-%H%M%S}-{secrets.token_hex(4)}"

    def _validate_thread_id(self, thread_id: str) -> str:
        if not THREAD_ID_RE.fullmatch(thread_id):
            raise ValueError("invalid thread_id")
        return thread_id

    def _normalize_title(self, title: str) -> str:
        normalized = " ".join(title.strip().split())
        if not normalized:
            return "New thread"
        return normalized[:120]

    def _normalize_role(self, role: str) -> str:
        normalized = role.strip().lower()
        if normalized not in {"user", "assistant"}:
            raise ValueError("role must be user or assistant")
        return normalized

    def _normalize_content(self, content: str) -> str:
        normalized = content.strip()
        if not normalized:
            raise ValueError("message content cannot be empty")
        return normalized

    def _render(self, thread: Thread) -> str:
        lines = [
            f"# {thread.title}",
            "",
            f"ARI_THREAD_ID: {thread.id}",
            f"CREATED_AT: {thread.created_at.isoformat()}",
            f"UPDATED_AT: {thread.updated_at.isoformat()}",
            "",
            "## Messages",
            "",
        ]
        for message in thread.messages:
            label = "User" if message.role == "user" else "ARI"
            stamp = (message.timestamp or thread.updated_at).isoformat()
            lines.extend([f"### {label} - {stamp}", "", message.content.strip(), ""])
        return "\n".join(lines).rstrip() + "\n"

    def _parse_thread(self, path: Path) -> Thread:
        content = path.read_text(encoding="utf-8")
        lines = content.splitlines()
        title = lines[0].removeprefix("# ").strip() if lines else path.stem
        metadata: dict[str, str] = {}
        messages: list[ThreadMessage] = []
        index = 1
        while index < len(lines):
            line = lines[index].strip()
            if line == "## Messages":
                index += 1
                break
            if ":" in line:
                key, value = line.split(":", 1)
                metadata[key.strip()] = value.strip()
            index += 1

        while index < len(lines):
            line = lines[index]
            if not line.startswith("### "):
                index += 1
                continue
            heading = line[4:].strip()
            role_label, _, raw_stamp = heading.partition(" - ")
            role = "user" if role_label.lower() == "user" else "assistant"
            index += 1
            if index < len(lines) and lines[index] == "":
                index += 1
            body: list[str] = []
            while index < len(lines) and not lines[index].startswith("### "):
                body.append(lines[index])
                index += 1
            text = "\n".join(body).strip()
            if text:
                messages.append(ThreadMessage(role=role, content=text, timestamp=self._parse_datetime(raw_stamp)))

        created_at = self._parse_datetime(metadata.get("CREATED_AT")) or self._path_datetime(path)
        updated_at = self._parse_datetime(metadata.get("UPDATED_AT")) or created_at
        thread_id = metadata.get("ARI_THREAD_ID") or path.stem
        return Thread(
            id=thread_id,
            title=title or "New thread",
            date=date(int(path.parents[2].name), int(path.parents[1].name), int(path.parent.name)),
            path=str(path.relative_to(self.root)),
            created_at=created_at,
            updated_at=updated_at,
            messages=messages,
        )

    def _thread_summary(self, path: Path) -> ThreadSummary:
        thread = self._parse_thread(path)
        return ThreadSummary(
            id=thread.id,
            title=thread.title,
            date=thread.date,
            path=thread.path,
            updated_at=thread.updated_at,
            message_count=len(thread.messages),
        )

    def _parse_datetime(self, value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)

    def _path_datetime(self, path: Path) -> datetime:
        stat = path.stat()
        return datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
