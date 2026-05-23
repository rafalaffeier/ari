# File Thread Storage

ARI chat threads are stored as lightweight Markdown files, not as SQL rows.

## Rule

- PostgreSQL is for account, auth, workspace, device, integration, sync metadata, and operational metadata.
- User chat/thread content must not be stored in PostgreSQL.
- A thread is a plain Markdown file under the workspace memory root.
- Files are readable by humans and selectively loadable by ARI.
- Encryption can be added later at the file/sync layer; local staging threads remain plaintext for product testing.

## Path

```text
{MEMORY_ROOT}/{workspace_id}/threads/YYYY/MM/DD/{thread_id}.md
```

Example:

```text
backend/data/memory/11111111-1111-1111-1111-111111111111/threads/2026/05/23/20260523-160102-a1b2c3d4.md
```

## Format

```md
# Thread title

ARI_THREAD_ID: 20260523-160102-a1b2c3d4
CREATED_AT: 2026-05-23T16:01:02+00:00
UPDATED_AT: 2026-05-23T16:04:30+00:00

## Messages

### User - 2026-05-23T16:01:02+00:00

User text.

### ARI - 2026-05-23T16:01:07+00:00

Assistant text.
```

The filename and metadata are operational. The source of truth remains the Markdown file body.

## API

- `GET /api/v1/messages/{workspace_id}/threads`
- `POST /api/v1/messages/{workspace_id}/threads`
- `GET /api/v1/messages/{workspace_id}/threads/{thread_id}`
- `POST /api/v1/messages/{workspace_id}/chat` accepts `thread_id`
- `POST /api/v1/messages/{workspace_id}/orchestrate` accepts `thread_id`
- `POST /api/v1/messages/{workspace_id}/voice` accepts `thread_id`

The web app creates a thread file before the first user message, then continues that same file.
