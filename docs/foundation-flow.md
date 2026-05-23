# Foundation Flow

This is the current local-first foundation. The source of truth for assistant memory is Markdown, while the backend exposes a small API to write, read, summarize-by-section, and search it.

```mermaid
flowchart TD
    U["User"] --> C["Desktop or Mobile Client"]
    C --> API["FastAPI Backend<br/>localhost:8000"]

    API --> MW["Memory API<br/>/api/v1/memory"]
    MW --> STORE["JournalStore"]
    STORE --> FILES["Markdown Memory Files<br/>backend/data/memory/{workspace}/journal/YYYY/MM/YYYY-MM-DD.md"]

    C --> W["Write Entry"]
    W --> POST["POST /journal/{date}/entries"]
    POST --> API

    C --> R["Read Day"]
    R --> GETDAY["GET /journal/{date}"]
    GETDAY --> API

    C --> O["Structured Overview"]
    O --> GETOV["GET /journal/{date}/overview"]
    GETOV --> API

    C --> S["Search Memory"]
    S --> SEARCH["GET /search?q=..."]
    SEARCH --> API

    FILES --> READ["Plain Markdown<br/>human-readable, portable"]
    FILES --> IDX["Future derived index<br/>rebuildable cache"]
```

## Request Flow

```mermaid
sequenceDiagram
    participant User
    participant Client as Desktop/Mobile Client
    participant API as FastAPI Backend
    participant Store as JournalStore
    participant Files as Markdown Files

    User->>Client: Add task, decision, fact, pending item
    Client->>API: POST /api/v1/memory/local/journal/2026-05-11/entries
    API->>Store: append_entry(workspace, date, section, text)
    Store->>Files: Create/update YYYY-MM-DD.md
    Files-->>Store: Saved
    Store-->>API: File path
    API-->>Client: 201 Created

    User->>Client: What happened on 2026-05-11?
    Client->>API: GET /api/v1/memory/local/journal/2026-05-11/overview
    API->>Store: overview(workspace, date)
    Store->>Files: Read Markdown
    Files-->>Store: Markdown content
    Store-->>API: Sections grouped as JSON
    API-->>Client: Tasks, decisions, pending, facts, technical_events
    Client-->>User: Shows structured answer
```

## Planned Secure Flow

```mermaid
flowchart TD
    C1["Desktop App"] --> ENC["Encrypt before upload"]
    C2["Mobile App"] --> DEC["Decrypt after download"]

    ENC --> API["Backend API"]
    DEC --> API

    API --> DB["Minimal PostgreSQL<br/>users, devices, sessions, file_versions"]
    API --> OBJ["Object Storage<br/>encrypted Markdown files"]

    OBJ -. "ciphertext only" .-> API
    DB -. "metadata only" .-> API

    C1 --> LOCAL["Local Markdown Memory"]
    LOCAL --> ENC
    DEC --> CACHE["Mobile local cache"]
```

## Current Implementation

- Memory root: `backend/data/memory`
- API module: `backend/app/api/v1/endpoints/memory.py`
- Store module: `backend/app/memory/journal.py`
- Tests: `backend/tests/unit/test_journal_store.py`, `backend/tests/integration/test_memory_api.py`
