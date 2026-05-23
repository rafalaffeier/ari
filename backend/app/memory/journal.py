from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

from .paths import ensure_inside_root, journal_path, validate_workspace_id


SECTION_TITLES = {
    "tasks": "Tasks",
    "decisions": "Decisions",
    "pending": "Pending",
    "facts": "Facts",
    "chat": "Chat",
    "technical_events": "Technical Events",
}


@dataclass(frozen=True)
class JournalEntry:
    section: str
    text: str
    timestamp: datetime | None = None


@dataclass(frozen=True)
class SearchResult:
    date: date
    path: str
    line_number: int
    line: str


@dataclass(frozen=True)
class DayOverview:
    date: date
    sections: dict[str, list[str]]


@dataclass(frozen=True)
class TimelineDay:
    date: date
    path: str
    entry_count: int
    sections: dict[str, int]


class JournalStore:
    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()

    def append_entry(self, workspace_id: str, day: date, entry: JournalEntry) -> Path:
        section = self._normalize_section(entry.section)
        text = self._normalize_entry_text(entry.text)
        path = ensure_inside_root(self.root, journal_path(self.root, workspace_id, day))
        path.parent.mkdir(parents=True, exist_ok=True)

        content = path.read_text(encoding="utf-8") if path.exists() else self._new_day_content(day)
        content = self._ensure_section(content, section)

        stamp = entry.timestamp or datetime.now(timezone.utc)
        line = f"- {stamp.strftime('%H:%M')} {text}"
        content = self._append_to_section(content, section, line)
        path.write_text(content, encoding="utf-8")
        return path

    def read_day(self, workspace_id: str, day: date) -> str:
        path = ensure_inside_root(self.root, journal_path(self.root, workspace_id, day))
        if not path.exists():
            return self._new_day_content(day)
        return path.read_text(encoding="utf-8")

    def overview(self, workspace_id: str, day: date) -> DayOverview:
        content = self.read_day(workspace_id, day)
        return DayOverview(date=day, sections=self._parse_sections(content))

    def timeline(self, workspace_id: str, limit: int = 30) -> list[TimelineDay]:
        validate_workspace_id(workspace_id)
        workspace_root = ensure_inside_root(self.root, self.root / workspace_id)
        journal_root = workspace_root / "journal"
        if not journal_root.exists():
            return []

        days: list[TimelineDay] = []
        for path in sorted(journal_root.glob("*/*/*.md"), reverse=True):
            day = date.fromisoformat(path.stem)
            sections = self._parse_sections(path.read_text(encoding="utf-8"))
            section_counts = {section: len(entries) for section, entries in sections.items()}
            days.append(
                TimelineDay(
                    date=day,
                    path=str(path.relative_to(self.root)),
                    entry_count=sum(section_counts.values()),
                    sections=section_counts,
                )
            )
            if len(days) >= limit:
                break
        return days

    def search(self, workspace_id: str, query: str, limit: int = 20) -> list[SearchResult]:
        validate_workspace_id(workspace_id)
        term = query.strip().lower()
        if not term:
            return []

        workspace_root = ensure_inside_root(self.root, self.root / workspace_id)
        journal_root = workspace_root / "journal"
        if not journal_root.exists():
            return []

        results: list[SearchResult] = []
        for path in sorted(journal_root.glob("*/*/*.md")):
            day = date.fromisoformat(path.stem)
            for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
                if term in line.lower():
                    results.append(SearchResult(day, str(path.relative_to(self.root)), line_number, line.strip()))
                    if len(results) >= limit:
                        return results
        return results

    def _new_day_content(self, day: date) -> str:
        sections = "\n\n".join(f"## {title}\n" for title in SECTION_TITLES.values())
        return f"# {day:%Y-%m-%d}\n\n{sections}\n"

    def _normalize_section(self, section: str) -> str:
        normalized = section.strip().lower()
        if normalized not in SECTION_TITLES:
            allowed = ", ".join(SECTION_TITLES)
            raise ValueError(f"section must be one of: {allowed}")
        return normalized

    def _normalize_entry_text(self, text: str) -> str:
        normalized = " ".join(text.strip().split())
        if not normalized:
            raise ValueError("entry text cannot be empty")
        return normalized

    def _ensure_section(self, content: str, section: str) -> str:
        heading = f"## {SECTION_TITLES[section]}"
        if heading in content:
            return content
        return content.rstrip() + f"\n\n{heading}\n"

    def _append_to_section(self, content: str, section: str, line: str) -> str:
        heading = f"## {SECTION_TITLES[section]}"
        lines = content.rstrip().splitlines()
        heading_index = lines.index(heading)

        insert_at = len(lines)
        for index in range(heading_index + 1, len(lines)):
            if lines[index].startswith("## "):
                insert_at = index
                break

        lines.insert(insert_at, line)
        return "\n".join(lines).rstrip() + "\n"

    def _parse_sections(self, content: str) -> dict[str, list[str]]:
        title_to_key = {title: key for key, title in SECTION_TITLES.items()}
        sections = {key: [] for key in SECTION_TITLES}
        current_key: str | None = None

        for raw_line in content.splitlines():
            line = raw_line.strip()
            if line.startswith("## "):
                current_key = title_to_key.get(line[3:].strip())
                continue
            if current_key is None or not line.startswith("- "):
                continue
            sections[current_key].append(line[2:].strip())

        return sections
