# Desktop Memory Contract

Phase 2 makes the desktop app the first real memory writer and reader.

The desktop app should not invent a second memory model. It should call the same protected backend memory API used by tests and future mobile clients.

## Required Configuration

```text
backend_url
access_token
default_workspace_id
local_memory_root
```

`access_token` must be stored in OS secure storage:

- macOS: Keychain
- Windows: Credential Manager / DPAPI
- Linux development fallback: local encrypted file or environment variable

## Required Desktop Commands

```text
append_journal_entry(section, text, timestamp?)
read_journal_day(date)
read_journal_overview(date)
search_memory(query, limit?)
```

## Backend Endpoints

```text
POST /api/v1/memory/{workspace_uuid}/journal/{YYYY-MM-DD}/entries
GET  /api/v1/memory/{workspace_uuid}/journal/{YYYY-MM-DD}
GET  /api/v1/memory/{workspace_uuid}/journal/{YYYY-MM-DD}/overview
GET  /api/v1/memory/{workspace_uuid}/search?q=...
```

All requests must include:

```text
Authorization: Bearer <access_token>
```

## Local-First Rule

The backend currently writes Markdown locally under `backend/data/memory`.

The desktop phase should prepare for a future where desktop also keeps a local memory folder. Until sync exists, the backend memory API remains the single implementation path for writes.

## Acceptance Criteria

- Desktop can append a `tasks` entry through the backend.
- Desktop can read a day overview.
- Desktop can search memory.
- Missing or invalid token returns a clear auth error.
- Workspace id comes from login/register response, not manual input.

## Current Scaffold

The initial Rust client scaffold lives in:

```text
desktop/Cargo.toml
desktop/tauri.conf.json
desktop/src/lib.rs
desktop/src/memory/client.rs
desktop/src/memory/mod.rs
desktop/examples/memory_smoke.rs
```

Initial Rust dependencies:

```toml
reqwest = { version = "0.12", features = ["json"] }
serde = { version = "1", features = ["derive"] }
serde_json = "1"
tauri = "2"
keyring = "3"
```
