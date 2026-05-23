# Escalation Plan

This plan controls how the product grows from the local foundation into a secure multi-device assistant.

## Product Design Source

The ARI Solara desktop UI is the canonical visual source for all client surfaces.

- Desktop, web, and mobile must share the same product identity: Solara, dark warm background, gold/rose accents, quiet borders, serif-led ARI branding, and focused assistant-first layouts.
- The website and mobile app should adapt the desktop design to their platform constraints instead of introducing a separate visual language.
- New UI work should check `desktop/ui/index.html` first before adding colors, typography, spacing, icons, or interaction patterns.

## Phase 0: Foundation

Status: complete

Goal: prove that Markdown memory can be created, read, searched, and exposed through a backend API.

Exit criteria:

- Memory writes create daily Markdown files.
- Memory can be read by date.
- Memory can be returned as structured sections.
- Memory can be searched by text.
- Tests cover journal store and API behavior.
- Local API smoke test passes.

## Phase 1: Identity and Workspace Safety

Status: mostly complete

Goal: stop using free-form `workspace_id` as trust input and bind memory access to authenticated users.

Build:

- JWT auth dependency. Done.
- `current_user` helper. Done.
- Workspace ownership/membership checks. Done for memory and workspace list/create.
- Default workspace creation on registration. Done.
- Memory endpoints derive workspace access from auth. Done.
- Replace public `local` workspace assumptions in API tests.

Exit criteria:

- Unauthenticated memory requests fail.
- Users can only access their own workspace memory.
- Registration creates a usable workspace.
- Tests prove cross-workspace access is blocked.

Evidence:

- Local Postgres/Redis launched on `5433`/`6380`.
- Alembic migration applied.
- Smoke test passed: register user A, register user B, user A writes memory, user A reads memory, user B receives `403`.
- Automated tests pass: `Ran 9 tests ... OK`.

## Phase 2: Local Desktop Agent Memory

Status: complete

Goal: make the desktop app the first real memory writer/reader.

Build:

- Desktop memory root configuration. Done in Tauri state with absolute-path validation.
- Desktop command for appending journal entries. Done.
- Desktop command for reading day overview. Done.
- Desktop command for searching memory. Done.
- Local file permission policy. Done for `open_file` with explicit `AI_ASSISTANT_ALLOWED_PATHS` allowlist and canonical path checks.
- Minimal desktop-to-backend API client. Done with login/register, bearer-auth memory calls, chat, recent conversations, audit events, tool catalog reads and backend action create/confirm/reject/result updates.
- ARI Solara desktop UI. Done for login/register, chat, memory search, backend-orchestrated local tool routing, backend-backed action confirmations and Activity log.
- Shared tool catalog. Done in `shared/tools/catalog.json` and served by `/api/v1/tools/`.
- Local desktop tools. Done for browser open, Mac Calendar list/create, Mac Reminders list/create, weather by city/device location, memory write/read/search.
- Audit event trail. Started with append-only `audit_logs`, hash chain fields, desktop `audit_tool_event`, and Activity view.
- Action API ownership. Updated so actions use authenticated `user_id`, authorized `workspace_id`, tool metadata, idempotency, and backend confirmation tokens.
- Desktop action bridge. Added Tauri commands and UI hooks so detected tools create backend actions before execution, confirm with backend tokens, reject pending backend actions when cancelled, and mark actions done/failed after local execution.
- ARI orchestration endpoint. Added model-backed `/messages/{workspace_id}/orchestrate` so normal conversation, clarifying questions and tool preparation are decided by the backend instead of UI regex.
- Removed the older parallel `/messages/{workspace_id}/interpret` path so the app has one primary orchestration brain.
- Device registration. Updated so devices register under the authenticated user and an authorized workspace.
- Agent WebSocket. Updated to require `device_id` and `agent_token`, and to maintain online/ping/offline device state.

Contract: see `docs/desktop-memory-contract.md`.

Evidence:

- Rust installed through Homebrew: `cargo 1.95.0`, `rustc 1.95.0`.
- Desktop crate compiles: `cargo check --manifest-path desktop/Cargo.toml`.
- Desktop crate tests pass: `cargo test --manifest-path desktop/Cargo.toml`.
- Desktop memory smoke passes against local backend: `DESKTOP_MEMORY_SMOKE_OK`.
- Initial Tauri UI added for login/register, append, day read, overview, and search.
- Desktop reset command added to clear persisted config and keychain token.
- Unsafe local memory roots are covered by Rust tests: empty, relative, and parent-segment paths are rejected.
- Tauri runtime starts with `cargo run --manifest-path desktop/Cargo.toml`; invalid placeholder icon was replaced with a valid 512x512 PNG.
- Filesystem policy tests cover allowed files plus empty, relative, missing, outside-root, and parent-segment escape paths.
- `/Users/rafalaffeier/Desktop/ARI.app` launcher was verified with macOS `open`; it starts backend and desktop.
- Backend listens on `127.0.0.1:8000` after launcher start.
- `cargo check --manifest-path desktop/Cargo.toml` passes after tool catalog, audit, actions, devices and WebSocket changes.
- Backend Python modules compile after action/auth/device/WebSocket changes.
- Backend unit/integration suite passes with `PYTHONPATH=backend backend/.venv/bin/python -m unittest discover -s backend/tests -p 'test_*.py'`.
- Backend tool catalog responds after relaunching `/Users/rafalaffeier/Desktop/ARI.app`.

Exit criteria:

- Desktop can write a task/decision/pending item.
- Desktop can read a day overview.
- Memory remains readable as Markdown outside the app.
- Unsafe paths are rejected.
- ARI.app opens reliably from Finder/macOS `open`.
- Action creation and confirmation are bound to authenticated users and authorized workspaces.
- Desktop UI routes tool confirmations through backend action tokens before local execution and sends final done/failed results back to backend.
- Backend orchestrator handles chat/thinking versus tool intent; UI keeps regex only as offline fallback behavior.
- Backend integration tests cover normal conversation orchestration and complete calendar action preparation.
- Backend orchestration now separates executable tools from planned tools, preventing ARI from claiming travel searches before a real provider is connected.
- Device registration and agent WebSocket reject unauthenticated devices.
- Final desktop memory acceptance passed with `cargo run --manifest-path desktop/Cargo.toml --example memory_smoke`: write, overview and search returned `DESKTOP_MEMORY_SMOKE_OK`.
- Backend tests pass: `14 tests OK`.
- Desktop tests pass: `20 tests OK`.

## Phase 3: Sync Model

Status: complete

Goal: prepare online access without turning memory into database content.

Build:

- `file_versions` metadata table. Done.
- Per-file checksum and version. Done for metadata and content uploads.
- Upload/download API for memory files. Done for Markdown content.
- Conflict detection. Done with `base_version` conflict response.
- Conflict preservation. Done by storing incoming conflicting content as a separate conflict Markdown file.
- Append-only sync events. Done for metadata create/update, content create/update, and content conflict events.
- Storage abstraction for local disk first, object storage later. Done with `LocalSyncStorage`.

Evidence:

- Migration applied: `20260523_0002_sync_metadata`.
- Backend sync metadata endpoints added under `/api/v1/sync/{workspace_id}`.
- Sync metadata smoke passed: `SYNC_METADATA_SMOKE_OK`, creating version 1, updating to version 2, and listing 2 events.
- Backend content sync endpoints added:
  - `PUT /api/v1/sync/{workspace_id}/files/content?path=...`
  - `GET /api/v1/sync/{workspace_id}/files/content?path=...`
- Content sync smoke passed: `SYNC_CONTENT_SMOKE_OK`, uploading Markdown v1, downloading v1, updating to v2, preserving a stale-client conflict copy, downloading the conflict copy, listing both files, and verifying `file_content.conflict`.
- Backend tests pass: `20 tests OK`.
- Desktop compile still passes: `cargo check --manifest-path desktop/Cargo.toml`.

Exit criteria:

- A client can upload a changed Markdown file. Done.
- Another client can download the latest version. Done.
- Conflicts preserve both versions. Done: the latest file remains current and the incoming stale edit is stored as a conflict file.
- Database contains metadata only, not memory content. Done for sync: Postgres stores path, version, checksum, size, timestamps, user, event metadata, envelope metadata, and `storage_key`; file bytes live in sync storage.

## Phase 4: Encryption

Status: complete

Goal: ensure server-side storage cannot read private memory.

Build:

- Client-side encryption envelope design. Done with `AES-256-GCM` envelope metadata on sync uploads.
- Backend encrypted-content contract. Done: content sync now requires encryption headers and stores/downloads ciphertext as `application/octet-stream`.
- Per-workspace memory key. Done for desktop: the workspace key is generated, serialized, stored in OS secure storage, and used by the crypto module.
- Device key wrapping contract. Done in backend with `workspace_key_wraps`; the backend stores opaque client-produced wraps and never unwraps them.
- Recovery phrase or recovery kit contract. Done in backend with `workspace_recovery_wraps`; the backend stores opaque client-produced recovery wraps and validates that hints do not contain secret material.
- Device revocation model. Done for key-wrap access: revoked devices can no longer read stored workspace key wraps.
- Signed URL strategy for storage. Deferred to Phase 7 because current storage is local disk behind the authenticated API; signed URLs become relevant with object storage.
- Server retention strategy. Deferred: for now, the server keeps the full synchronized memory copy as ciphertext while devices may keep local Markdown caches.

Evidence:

- Migration added: `20260523_0003_sync_encryption_metadata`.
- Migration added: `20260523_0004_workspace_key_wraps`.
- Migration added: `20260523_0005_workspace_recovery_wraps`.
- `file_versions.encryption_metadata` stores envelope metadata without plaintext.
- `workspace_key_wraps` stores opaque device-specific wrapped workspace keys without server-side unwrapping.
- `workspace_recovery_wraps` stores opaque recovery-phrase-wrapped workspace keys without server-side unwrapping.
- Backend content sync records ciphertext checksum and ciphertext size.
- Encryption smoke passed: `SYNC_ENCRYPTION_SMOKE_OK`, encrypting Markdown client-side with AES-GCM, uploading ciphertext, downloading ciphertext, decrypting locally, and preserving encrypted conflict content.
- Key wrap smoke passed: `SYNC_KEY_WRAP_SMOKE_OK`, registering a device, storing an opaque wrapped workspace key, reading it, revoking the device, and confirming revoked key access returns `403`.
- Recovery smoke passed: `SYNC_RECOVERY_SMOKE_OK`, storing an opaque recovery wrapped key, reading it, and rejecting recovery hints that include secret material.
- Desktop crypto tests pass: local AES-256-GCM encrypt/decrypt round-trip, path-bound AAD rejection, and workspace key base64 round-trip.
- Desktop client methods added for encrypted sync upload/download.
- Desktop client methods added for device key wraps and recovery wraps.
- Desktop Tauri commands added for workspace key creation and deletion backed by Keychain.
- Backend tests pass: `26 tests OK`.
- Desktop tests pass: `22 tests OK`.

Exit criteria:

- Server stores ciphertext only. Done for sync content uploads by requiring encryption envelope metadata and storing ciphertext checksums/sizes.
- Revoked devices cannot download new file keys. Done for stored key wraps: revoked devices receive `403`.
- Recovery flow is documented and testable. Done with recovery-wrap endpoints, contract docs, and smoke test.
- Metadata avoids sensitive content. Done for Phase 4 with envelope metadata only and metadata-safe sync path enforcement.

## Phase 5: Mobile Read/Write

Goal: make memory usable away from the desktop.

Build:

- Mobile auth. Done with login/register session persistence in the Expo app.
- Memory timeline screen. Done against `/memory/{workspace_id}/timeline`.
- Day overview screen. Done with cached overview and raw Markdown day content.
- Add entry form. Done with section selection and offline write queue.
- Search screen. Done with cached search fallback.
- Offline cache. Done with AsyncStorage-backed session, timeline, day, overview, search, and pending entries.

Exit criteria:

- Mobile can create an entry. Implemented via the protected memory API.
- Mobile can read a day. Implemented via day and overview views.
- Mobile can search synced memory. Implemented via search view.
- Mobile handles offline state clearly. Implemented with an offline cache status and queued entries.

## Phase 6: AI Recall

Status: complete

Goal: let the assistant answer questions using the Markdown memory layer.

Build:

- Date-based retrieval. Done for ISO dates in user messages.
- Relative date retrieval. Done for `today`/`hoy`, `yesterday`/`ayer`, `this week`/`esta semana`, and `this month`/`este mes`.
- Recent-range retrieval. Done for `last N days`, `últimos N días`, `recently`, `lately`, and `últimamente`.
- Text search retrieval. Done with query extraction and ranked partial-term matching.
- Monthly/weekly summary retrieval. Done for existing `summaries/YYYY-Www.md` and `summaries/YYYY-MM.md` files, with daily-journal fallback when summary files do not exist.
- Prompt context builder. Done in `backend/app/memory/recall.py`.
- Citation back to source files and lines. Done in recall prompts as `path:line` sources.
- Guardrails for missing/ambiguous memory. Done for missing recall sources: recall intent without matches adds an explicit no-invention instruction to the model context.
- Recall inspection endpoint. Done at `POST /api/v1/messages/{workspace_id}/recall` without requiring OpenAI.

Exit criteria:

- "What happened on DATE?" reads the right file. Covered by unit/integration tests for `2026-05-11`.
- "When did we discuss TOPIC?" searches relevant files. Covered by unit tests.
- Answers cite journal dates. Prompt context includes journal path and line citations.
- The model does not need to ingest the full memory folder. Done: recall limits to selected date/search snippets.
- Automatic summary generation is intentionally not part of Phase 6; this phase retrieves summary files when present.

Evidence:

- Backend recall tests pass: `Ran 31 tests ... OK (skipped=11)`.
- Mobile typecheck still passes after recall changes.
- Authenticated HTTP smoke passed against a fresh local backend: `PHASE6_RECALL_SMOKE_OK`.
- Smoke covered date recall, topic recall, recent-range recall, missing-memory guardrails, source citations, and workspace-authenticated API access.

## Phase 7: Production Staging

Status: started

Goal: deploy the backend only after the product foundation is safe and useful.

Build:

- Docker deployment profile. Started with `infra/docker/docker-compose.staging.yml` and Plesk-specific `infra/docker/docker-compose.plesk.yml`.
- HTTPS. Started with standalone Nginx TLS proxy config under `infra/docker/nginx/default.conf`; Plesk deployment uses Plesk TLS plus `infra/docker/nginx/plesk-additional-directives.conf`.
- PostgreSQL backup plan. Started with custom-format dump and restore scripts under `infra/docker/scripts/`.
- Redis deployment. Started with Redis persistence, password configuration, and healthcheck in the staging compose file.
- Object storage. Started with S3-compatible sync storage configuration and MinIO staging service.
- Logs and metrics. Started with container log commands and baseline metrics in `docs/production-staging-runbook.md`.
- Rate limiting. Started with Redis-backed fixed-window middleware enabled by staging config.
- Admin runbook. Started in `docs/production-staging-runbook.md`.

Exit criteria:

- Staging can be rebuilt from documented steps.
- Backups are restorable.
- Secrets are not committed.
- `8069` remains unused.
- Basic security checklist passes.

Evidence:

- Staging runbook added: `docs/production-staging-runbook.md`.
- Staging compose avoids `8069`; default host mappings are `8080:80` and `8443:443`.
- `ari.flusscreative.com` public staging domain created in Plesk and verified online with HTTPS default page.
- Plesk profile binds backend to `127.0.0.1:18000` and relies on Plesk nginx reverse proxy.
- `.env.staging`, TLS private keys, and backup dumps are ignored by `.gitignore`.
- Backend staging/production config rejects the default `SECRET_KEY`.
- `/ready` now checks database and Redis connectivity.
- Sync object storage can be selected with `SYNC_STORAGE_BACKEND=s3`; local remains the developer default.
- Rate limiting is configurable with `RATE_LIMIT_ENABLED`, `RATE_LIMIT_REQUESTS`, and `RATE_LIMIT_WINDOW_SECONDS`.

## Control Rules

- Do not add semantic search before Phase 6.
- Do not add cloud sync before Phase 3.
- Do not store memory content in PostgreSQL.
- Do not build mobile screens before auth and workspace safety are in place.
- Keep Markdown files as the source of truth.
- Treat indexes, embeddings, and caches as rebuildable derived data.
