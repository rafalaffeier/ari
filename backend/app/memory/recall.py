from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from .journal import JournalStore
from .paths import ensure_inside_root, journal_path


DATE_RE = re.compile(r"\b(20\d{2}-\d{2}-\d{2})\b")
MONTH_RE = re.compile(r"\b(20\d{2})-(0[1-9]|1[0-2])\b(?!-)")
WEEK_RE = re.compile(r"\b(20\d{2})-W(0[1-9]|[1-4]\d|5[0-3])\b", re.IGNORECASE)
LAST_DAYS_RE = re.compile(r"\b(?:last|últimos|ultimos)\s+([1-9]\d?)\s+(?:days|días|dias)\b", re.IGNORECASE)
WORD_RE = re.compile(r"[a-zA-Z0-9À-ÿ_-]{3,}")

STOPWORDS = {
    "about",
    "cuando",
    "cuándo",
    "date",
    "did",
    "discuss",
    "discutimos",
    "happen",
    "happened",
    "hablamos",
    "last",
    "memoria",
    "memory",
    "mes",
    "month",
    "pasada",
    "pasado",
    "paso",
    "pasó",
    "que",
    "qué",
    "recordamos",
    "remember",
    "resume",
    "resumen",
    "semana",
    "sobre",
    "summarize",
    "the",
    "this",
    "what",
    "when",
    "week",
}


@dataclass(frozen=True)
class RecallSource:
    date: date
    path: str
    line_number: int
    line: str
    reason: str
    source_date: str | None = None


@dataclass(frozen=True)
class MemoryContext:
    sources: list[RecallSource]
    prompt: str
    recall_intent: bool = False


def build_memory_context(
    store: JournalStore,
    workspace_id: str,
    user_message: str,
    limit: int = 8,
    current_date: date | None = None,
) -> MemoryContext:
    if limit <= 0:
        return MemoryContext(sources=[], prompt="")

    anchor_date = current_date or date.today()
    recall_intent = _looks_like_recall_request(user_message)
    sources: list[RecallSource] = []

    for year, week in _extract_weeks(user_message, anchor_date):
        weekly_sources = _recall_summary(
            store,
            workspace_id,
            f"{year}-W{week:02d}.md",
            "weekly-summary",
            remaining=limit - len(sources),
        )
        if not weekly_sources:
            start, end = _week_range(year, week)
            weekly_sources = _recall_journal_range(
                store,
                workspace_id,
                start,
                end,
                "weekly-journal",
                remaining=limit - len(sources),
            )
        sources.extend(weekly_sources)
        if len(sources) >= limit:
            break

    for year, month in _extract_months(user_message, anchor_date):
        monthly_sources = _recall_summary(
            store,
            workspace_id,
            f"{year}-{month:02d}.md",
            "monthly-summary",
            remaining=limit - len(sources),
        )
        if not monthly_sources:
            start, end = _month_range(year, month)
            monthly_sources = _recall_journal_range(
                store,
                workspace_id,
                start,
                end,
                "monthly-journal",
                remaining=limit - len(sources),
            )
        sources.extend(monthly_sources)
        if len(sources) >= limit:
            break

    dates = _extract_dates(user_message, anchor_date)

    for day in dates:
        sources.extend(_recall_by_date(store, workspace_id, day, remaining=limit - len(sources)))
        if len(sources) >= limit:
            break

    for start, end in _extract_recent_ranges(user_message, anchor_date):
        recent_sources = _recall_journal_range(
            store,
            workspace_id,
            start,
            end,
            "recent-journal",
            remaining=limit - len(sources),
        )
        sources.extend(recent_sources)
        if len(sources) >= limit:
            break

    remaining = limit - len(sources)
    query = _extract_query(user_message)
    if remaining > 0 and query:
        for source in _recall_by_query(store, workspace_id, query, remaining=remaining):
            if source not in sources:
                sources.append(source)
            if len(sources) >= limit:
                break

    return MemoryContext(sources=sources, prompt=_format_prompt(sources, recall_intent), recall_intent=recall_intent)


def _extract_dates(message: str, current_date: date) -> list[date]:
    days: list[date] = []
    for raw in DATE_RE.findall(message):
        try:
            parsed = date.fromisoformat(raw)
        except ValueError:
            continue
        if parsed not in days:
            days.append(parsed)
    lower = message.lower()
    if _contains_any(lower, ("today", "hoy")) and current_date not in days:
        days.append(current_date)
    yesterday = current_date - timedelta(days=1)
    if _contains_any(lower, ("yesterday", "ayer")) and yesterday not in days:
        days.append(yesterday)
    return days


def _extract_weeks(message: str, current_date: date) -> list[tuple[int, int]]:
    weeks: list[tuple[int, int]] = []
    for raw_year, raw_week in WEEK_RE.findall(message):
        item = (int(raw_year), int(raw_week))
        if item not in weeks:
            weeks.append(item)
    lower = message.lower()
    if _contains_any(lower, ("this week", "esta semana")):
        iso = current_date.isocalendar()
        item = (iso.year, iso.week)
        if item not in weeks:
            weeks.append(item)
    if _contains_any(lower, ("last week", "semana pasada")):
        iso = (current_date - timedelta(days=7)).isocalendar()
        item = (iso.year, iso.week)
        if item not in weeks:
            weeks.append(item)
    return weeks


def _extract_months(message: str, current_date: date) -> list[tuple[int, int]]:
    without_dates = DATE_RE.sub(" ", message)
    months: list[tuple[int, int]] = []
    for raw_year, raw_month in MONTH_RE.findall(without_dates):
        item = (int(raw_year), int(raw_month))
        if item not in months:
            months.append(item)
    lower = message.lower()
    if _contains_any(lower, ("this month", "este mes")):
        item = (current_date.year, current_date.month)
        if item not in months:
            months.append(item)
    if _contains_any(lower, ("last month", "mes pasado")):
        year = current_date.year
        month = current_date.month - 1
        if month == 0:
            year -= 1
            month = 12
        item = (year, month)
        if item not in months:
            months.append(item)
    return months


def _extract_recent_ranges(message: str, current_date: date) -> list[tuple[date, date]]:
    ranges: list[tuple[date, date]] = []
    lower = message.lower()
    for raw_days in LAST_DAYS_RE.findall(message):
        days = max(1, min(30, int(raw_days)))
        ranges.append((current_date - timedelta(days=days - 1), current_date))
    if _contains_any(lower, ("recently", "lately", "últimamente", "ultimamente", "recent memory", "memoria reciente")):
        ranges.append((current_date - timedelta(days=6), current_date))

    unique: list[tuple[date, date]] = []
    for item in ranges:
        if item not in unique:
            unique.append(item)
    return unique


def _contains_any(text: str, markers: tuple[str, ...]) -> bool:
    return any(marker in text for marker in markers)


def _looks_like_recall_request(message: str) -> bool:
    lower = message.lower()
    if DATE_RE.search(message) or WEEK_RE.search(message) or MONTH_RE.search(message):
        return True
    if LAST_DAYS_RE.search(message):
        return True
    return _contains_any(
        lower,
        (
            "ayer",
            "cuando",
            "cuándo",
            "did we discuss",
            "do you remember",
            "esta semana",
            "este mes",
            "happened",
            "hablamos",
            "hoy",
            "lately",
            "memory",
            "pasó",
            "que pasó",
            "qué pasó",
            "recent memory",
            "recently",
            "recuerdas",
            "remember",
            "this month",
            "this week",
            "today",
            "what happened",
            "when did",
            "yesterday",
            "últimamente",
            "ultimamente",
        ),
    )


def _extract_query(message: str) -> str:
    without_dates = LAST_DAYS_RE.sub(" ", WEEK_RE.sub(" ", DATE_RE.sub(" ", MONTH_RE.sub(" ", message))))
    words = [word for word in WORD_RE.findall(without_dates) if word.lower() not in STOPWORDS]
    return " ".join(words[:8]).strip()


def _recall_by_date(store: JournalStore, workspace_id: str, day: date, remaining: int) -> list[RecallSource]:
    if remaining <= 0:
        return []
    content = store.read_day(workspace_id, day)
    path = journal_path(Path(store.root), workspace_id, day).relative_to(store.root)
    sources: list[RecallSource] = []
    for line_number, raw_line in enumerate(content.splitlines(), start=1):
        line = raw_line.strip()
        if not line.startswith("- "):
            continue
        sources.append(
            RecallSource(
                date=day,
                path=str(path),
                line_number=line_number,
                line=line,
                reason="date-match",
            )
        )
        if len(sources) >= remaining:
            break
    return sources


def _recall_journal_range(
    store: JournalStore,
    workspace_id: str,
    start: date,
    end: date,
    reason: str,
    remaining: int,
) -> list[RecallSource]:
    if remaining <= 0:
        return []
    sources: list[RecallSource] = []
    current = start
    while current <= end and len(sources) < remaining:
        sources.extend(_recall_by_date(store, workspace_id, current, remaining=remaining - len(sources)))
        current += timedelta(days=1)
    return [
        RecallSource(
            date=source.date,
            path=source.path,
            line_number=source.line_number,
            line=source.line,
            reason=reason,
            source_date=source.source_date,
        )
        for source in sources[:remaining]
    ]


def _week_range(year: int, week: int) -> tuple[date, date]:
    start = date.fromisocalendar(year, week, 1)
    return start, start + timedelta(days=6)


def _month_range(year: int, month: int) -> tuple[date, date]:
    start = date(year, month, 1)
    if month == 12:
        next_month = date(year + 1, 1, 1)
    else:
        next_month = date(year, month + 1, 1)
    return start, next_month - timedelta(days=1)


def _recall_summary(
    store: JournalStore,
    workspace_id: str,
    filename: str,
    reason: str,
    remaining: int,
) -> list[RecallSource]:
    if remaining <= 0:
        return []
    path = ensure_inside_root(Path(store.root), Path(store.root) / workspace_id / "summaries" / filename)
    if not path.exists():
        return []

    if reason == "weekly-summary":
        year, week = filename.removesuffix(".md").split("-W")
        source_day = date.fromisocalendar(int(year), int(week), 1)
    else:
        year, month = filename.removesuffix(".md").split("-")
        source_day = date(int(year), int(month), 1)

    sources: list[RecallSource] = []
    relative_path = path.relative_to(store.root)
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        sources.append(
            RecallSource(
                date=source_day,
                path=str(relative_path),
                line_number=line_number,
                line=line,
                reason=reason,
                source_date=filename.removesuffix(".md"),
            )
        )
        if len(sources) >= remaining:
            break
    return sources


def _recall_by_query(store: JournalStore, workspace_id: str, query: str, remaining: int) -> list[RecallSource]:
    if remaining <= 0:
        return []
    terms = [word.lower() for word in WORD_RE.findall(query) if word.lower() not in STOPWORDS]
    if not terms:
        return []

    workspace_root = ensure_inside_root(Path(store.root), Path(store.root) / workspace_id)
    journal_root = workspace_root / "journal"
    if not journal_root.exists():
        return []

    ranked: list[tuple[int, date, int, str, str]] = []
    exact_query = query.lower()
    for path in sorted(journal_root.glob("*/*/*.md")):
        day = date.fromisoformat(path.stem)
        for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            line = raw_line.strip()
            if not line.startswith("- "):
                continue
            lower = line.lower()
            matches = sum(1 for term in terms if term in lower)
            if matches == 0:
                continue
            exact_bonus = len(terms) if exact_query in lower else 0
            ranked.append((matches + exact_bonus, day, line_number, str(path.relative_to(store.root)), line))

    ranked.sort(key=lambda item: (-item[0], item[1], item[2]))
    return [
        RecallSource(
            date=day,
            path=path,
            line_number=line_number,
            line=line,
            reason="text-search",
        )
        for _, day, line_number, path, line in ranked[:remaining]
    ]


def _format_prompt(sources: list[RecallSource], recall_intent: bool) -> str:
    if not sources:
        if not recall_intent:
            return ""
        return (
            "The user appears to be asking for memory recall, but no matching memory sources were found. "
            "Say that the available memory is not enough, and do not invent dates, events, or details."
        )
    lines = [
        "Use only these memory sources when recalling past events. Cite dates or file:line references. "
        "If they are insufficient, say the memory is not enough."
    ]
    for source in sources:
        label = source.source_date or source.date.isoformat()
        lines.append(
            f"- [{source.reason}] {label} {source.path}:{source.line_number}: {source.line}"
        )
    return "\n".join(lines)
