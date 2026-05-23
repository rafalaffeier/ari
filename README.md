# AI Assistant

Multi-device AI assistant — FastAPI · PostgreSQL · Redis · Tauri · React Native

## Quick Start (backend)

```bash
cd backend
cp .env.example .env.local    # fill in your values
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
docker compose -f ../infra/docker/docker-compose.yml up db redis -d
PYTHONPATH=. alembic upgrade head
uvicorn app.main:app --reload
```

Docs: http://localhost:8000/docs

Local ports:

- Backend API: http://localhost:8000
- PostgreSQL: localhost:5433
- Redis: localhost:6380

Port `8069` is intentionally unused because it is reserved for another local project.

## Quick Start (desktop)

```bash
cd desktop
cargo check
cargo run
```

For fast desktop iteration, keep the `cargo run` window open and edit files under `desktop/ui`.
Press `Cmd+R` on macOS or `Ctrl+R` on Windows/Linux inside the desktop window to reload the
current HTML/CSS/JS without reinstalling the app. Rust/Tauri command changes still require stopping
and re-running `cargo run`, but they do not require reinstalling either.

The desktop app points at `https://ari.flusscreative.com` by default. To test against a local backend:

```bash
AI_ASSISTANT_BACKEND_URL="http://127.0.0.1:8000" cargo run
```

The desktop crate exposes Tauri commands for backend login/register and Phase 2 memory access:

```text
login
register
configure_desktop
load_desktop_config
clear_desktop_config
append_journal_entry
read_journal_day
read_journal_overview
search_memory
```

The initial desktop window in `desktop/ui/index.html` can register/login, append journal entries,
read a Markdown day, read an overview, and search memory through those commands.

Desktop filesystem tools require an explicit local allowlist before they can open files:

```bash
AI_ASSISTANT_ALLOWED_PATHS="/Users/you/Documents:/tmp/ai-assistant-memory" cargo run
```

Desktop memory smoke:

```bash
cd ..
cargo run --manifest-path desktop/Cargo.toml --example memory_smoke
```

## Quick Start (mobile)

```bash
cd mobile
npm install
EXPO_PUBLIC_API_URL="http://localhost:8000/api/v1" npm run start
```

On a physical phone, point `EXPO_PUBLIC_API_URL` at the computer's LAN address instead of `localhost`.

## Structure

```
ai-assistant/
├── backend/         # FastAPI — API, models, tools, jobs
├── desktop/         # Tauri — desktop agent
├── mobile/          # React Native — mobile app
├── shared/          # Types and constants shared across clients
├── infra/           # Docker, nginx, scripts
└── docs/            # Architecture docs
```

## Development Steps (from architecture doc)

1. [x] Repo structure
2. [x] Local Markdown memory foundation
3. [ ] Auth + workspaces (JWT)
4. [ ] Device registration + WebSocket
5. [ ] Tool registry
6. [ ] First desktop tool: open_file
7. [ ] First backend tool: Google Calendar
8. [ ] Confirmation flow
9. [ ] Audit logging

Controlled escalation is tracked in [docs/escalation-plan.md](docs/escalation-plan.md).

## Memory Foundation

The first local-first memory layer stores daily journals as Markdown files under `backend/data/memory`.
Memory endpoints require bearer authentication and workspace access.

Endpoints:

```text
POST /api/v1/memory/{workspace_uuid}/journal/{YYYY-MM-DD}/entries
GET  /api/v1/memory/{workspace_uuid}/timeline
GET  /api/v1/memory/{workspace_uuid}/journal/{YYYY-MM-DD}
GET  /api/v1/memory/{workspace_uuid}/journal/{YYYY-MM-DD}/overview
GET  /api/v1/memory/{workspace_uuid}/journal/today
GET  /api/v1/memory/{workspace_uuid}/search?q=...
POST /api/v1/messages/{workspace_uuid}/recall
```

Recall supports ISO dates, weekly/monthly summary names, and basic relative dates such as
`today`, `yesterday`, `this week`, `this month`, `hoy`, `ayer`, `esta semana`, and `este mes`.
Weekly/monthly summaries are used when present; otherwise recall falls back to matching daily journal entries
inside the requested week or month.
Recent-range recall supports `last N days`, `últimos N días`, `recently`, `lately`, and `últimamente`.

Example entry:

```json
{
  "section": "tasks",
  "text": "Created the local Markdown memory foundation."
}
```
