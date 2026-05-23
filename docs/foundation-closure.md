# Foundation Closure

Status: closed

Date: 2026-05-11

## Scope

The foundation phase validates the core product direction:

- Assistant memory is local-first.
- The source of truth is Markdown files.
- The backend exposes a small API over that memory.
- Search and day-level recall work without a database-backed memory model.
- The future server can synchronize encrypted files without becoming the memory source of truth.

## Delivered

- Markdown journal storage under `backend/data/memory`.
- Safe workspace path validation.
- Daily journal file layout:

```text
backend/data/memory/{workspace_id}/journal/YYYY/MM/YYYY-MM-DD.md
```

- Memory API endpoints:

```text
POST /api/v1/memory/{workspace_id}/journal/{YYYY-MM-DD}/entries
GET  /api/v1/memory/{workspace_id}/journal/{YYYY-MM-DD}
GET  /api/v1/memory/{workspace_id}/journal/{YYYY-MM-DD}/overview
GET  /api/v1/memory/{workspace_id}/journal/today
GET  /api/v1/memory/{workspace_id}/search?q=...
```

- Structured sections:
  - `tasks`
  - `decisions`
  - `pending`
  - `facts`
  - `technical_events`

- Unit tests for journal storage.
- Integration tests for API behavior.
- Live local API smoke test on `127.0.0.1:8000`.
- Mermaid flow diagrams in `docs/foundation-flow.md`.
- Editable architecture reference in `docs/architecture-reference.md`.

## Verified

```text
Ran 8 tests in 0.037s
OK
```

Live endpoint checks completed:

- `GET /health`
- `POST /api/v1/memory/local/journal/2026-05-11/entries`
- `GET /api/v1/memory/local/journal/2026-05-11/overview`
- `GET /api/v1/memory/local/search?q=Markdown`

## Non-Goals

These were intentionally left out of foundation:

- Real user authentication.
- Workspace membership enforcement.
- Cloud sync.
- End-to-end encryption.
- Semantic search or embeddings.
- Desktop app integration.
- Mobile app integration.
- OpenAI answer generation over memory.

## Current Risks

- `workspace_id` is still passed directly in the URL.
- Memory files are plaintext local files.
- Search is simple case-insensitive line matching.
- Concurrent writes are not yet locked.
- No sync conflict handling exists.

## Foundation Decision

The foundation is accepted. The next phase should secure and bind this memory layer to real users and workspaces before building desktop/mobile UX on top of it.
