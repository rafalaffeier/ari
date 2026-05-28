# Google Workspace Connections Plan

This document is the working reference for adding Google Drive, Gmail, Calendar,
and Contacts as connected apps in ARI.

The product idea is not a generic "plugin store" yet. For the user, this should
feel like a simple **Connected apps** area where ARI asks for the minimum Google
permissions needed to help with files, calendar events, contacts, and email.

## Current Foundation

ARI already has the right backend shape for this:

- Google OAuth login exists.
- Google integration OAuth exists under `/api/v1/integrations/google/*`.
- Google tokens are stored encrypted in PostgreSQL through the `integrations` table.
- Calendar event and Contacts search endpoints already exist.
- PostgreSQL must remain limited to auth, integration metadata, encrypted tokens,
  and operational metadata.
- Chat threads, summaries, and assistant history must continue to live in
  Markdown/text files, not PostgreSQL.

Important constraint:

- Do not store raw Google Drive files, Gmail bodies, or long user content in
  PostgreSQL.
- If ARI summarizes or discusses a file/email, that conversation belongs in the
  Markdown thread history.
- If we cache external file/email metadata, keep it minimal and user-scoped.

## Product Shape

User-facing name:

- Preferred: **Connected apps**
- Spanish UI option: **Apps conectadas**
- Avoid calling it "plugins" in the main UI for now. "Plugin" sounds technical
  and open-ended, while this feature is about user trust and permissions.

Entry points:

- Sidebar icon: plug, puzzle, or connected-nodes icon.
- Settings/profile area: "Apps conectadas".
- Contextual chat prompts when ARI needs a permission.

Example contextual prompt:

> Puedo ayudarte con ese documento, pero necesito acceso a Google Drive. ¿Quieres conectarlo ahora?

Example connected-apps card:

```text
Google Workspace
Drive, Gmail, Agenda y Contactos

Conecta Google para que ARI pueda ayudarte con archivos, emails, agenda y personas.

[Conectar Google]
```

After connection, show granular status:

- Calendar: connected / not connected
- Contacts: connected / not connected
- Drive search: connected / not connected
- Drive file reading: connected / not connected
- Gmail reading: connected / not connected
- Gmail drafts/send: connected / not connected

## Permission Strategy

Ask for permissions incrementally. Do not ask for Drive, Gmail read, and Gmail
send all at once during onboarding.

Why:

- Users understand permissions better when the request appears at the moment they
  need it.
- Google expects apps to request the minimum relevant scopes.
- Gmail and broad Drive scopes can trigger sensitive/restricted verification.

Recommended flow:

1. User signs in normally.
2. ARI offers optional Google connection for productivity tasks.
3. First connection can include low-risk/basic scopes already supported by the app.
4. When the user asks for a Drive task, request Drive scope.
5. When the user asks for an email task, request Gmail scope.
6. For sending email, require explicit final confirmation every time.

## Scope Plan

Use the narrowest scope that supports the feature.

### Calendar

Existing direction:

- `https://www.googleapis.com/auth/calendar.events`

Use cases:

- Create events.
- Read upcoming events if we add list/read capability.

### Contacts

Existing direction:

- `https://www.googleapis.com/auth/contacts.readonly`

Use cases:

- Search contacts by name/email/phone.
- Help address emails or calendar invitations.

### Google Drive

Phase 1, search/list only:

- `https://www.googleapis.com/auth/drive.metadata.readonly`

Use cases:

- Search files by name.
- List recent files.
- Filter by MIME type, owner, modified date.
- Let the user pick which file ARI should inspect.

Phase 2, read selected files:

- `https://www.googleapis.com/auth/drive.readonly`

Use cases:

- Read selected Google Docs, text files, PDFs where supported.
- Summarize selected files.
- Answer questions about selected files.

Phase 3, create files controlled by ARI:

- `https://www.googleapis.com/auth/drive.file`

Use cases:

- Create a Google Doc from a summary.
- Save a generated document.
- Work only with files ARI created or the user explicitly opened with ARI.

Decision note:

- Prefer `drive.metadata.readonly` first for discovery.
- Add `drive.readonly` only when the product actually reads content.
- Consider Google Picker plus `drive.file` for safer user-selected file access.

### Gmail

Phase 1, read/search:

- `https://www.googleapis.com/auth/gmail.readonly`

Use cases:

- Find relevant emails.
- Summarize a thread.
- Show pending emails.
- Extract dates, names, and tasks.

Phase 2, drafts:

- `https://www.googleapis.com/auth/gmail.compose`

Use cases:

- Create a draft reply.
- Let the user review and send manually in Gmail.

Phase 3, send:

- `https://www.googleapis.com/auth/gmail.send`

Use cases:

- Send an email only after explicit confirmation.

Hard rule:

- ARI must never send email automatically.
- Before sending, ARI must show recipient, subject, body, and attachments if any.
- User must confirm the final send action.

Example confirmation:

```text
Voy a enviar este email:

Para: cliente@example.com
Asunto: Confirmacion de reunion

Contenido:
...

¿Confirmas el envio?
```

## UX States

Connected-app cards should have clear states:

- Not connected
- Connecting
- Connected
- Needs more permissions
- Expired/reconnect required
- Error

Chat status labels should be specific:

- `ARI esta buscando en Drive`
- `ARI esta leyendo el documento`
- `ARI esta revisando emails`
- `ARI esta preparando un borrador`
- `ARI esta creando un evento`
- `No pude conectar con Google. Revisa permisos o vuelve a conectar.`

Avoid vague states such as:

- `ARI esta pensando` for long external operations
- `Esta en proceso` when no real job/tool is running

## Backend Architecture

Reuse the existing `integrations` model:

- `provider = "google"`
- encrypted access token
- encrypted refresh token
- scopes list
- status
- expiry

Add service modules:

- `backend/app/services/google_drive.py`
- `backend/app/services/gmail.py`

Add endpoints under existing integrations or dedicated API routes:

- `GET /api/v1/integrations/google/status`
- `POST /api/v1/integrations/google/start`
- `GET /api/v1/integrations/google/drive/files`
- `GET /api/v1/integrations/google/drive/files/{file_id}/content`
- `GET /api/v1/integrations/google/gmail/messages`
- `GET /api/v1/integrations/google/gmail/messages/{message_id}`
- `POST /api/v1/integrations/google/gmail/drafts`
- `POST /api/v1/integrations/google/gmail/send`

Use shared helpers:

- `_valid_google_access_token(...)`
- encrypted token refresh flow
- scope checks before each operation

Add scope validation:

- If Drive metadata scope is missing, return a clear `needs_scope` response.
- If Gmail send scope is missing, return a clear `needs_scope` response.
- The UI can use this to show a connect/upgrade-permissions prompt.

## Tool Catalog

Add tools gradually to `shared/tools/catalog.json`.

Suggested tools:

- `search_google_drive_files`
- `read_google_drive_file`
- `search_gmail_messages`
- `read_gmail_thread`
- `create_gmail_draft`
- `send_gmail_message`

Risk levels:

- Search/list/read: low to medium, depending on data exposure.
- Create draft: medium.
- Send email: high, confirmation required.

Confirmation rules:

- Reading a user-selected file can be no confirmation after Drive is connected,
  but ARI should state what it is reading.
- Sending email always requires confirmation.
- Creating drafts should show a review step.

## Data Handling Rules

Do:

- Store OAuth tokens encrypted.
- Store only minimal integration metadata in PostgreSQL.
- Store conversations and summaries in Markdown thread files.
- Keep audit events for sensitive actions such as email send.
- Redact secrets and tokens from logs.

Do not:

- Store raw email bodies in PostgreSQL.
- Store raw Drive file contents in PostgreSQL.
- Commit tokens, client secrets, refresh tokens, or sample private data.
- Use Google data for training, advertising, resale, or unrelated purposes.

## Verification and Policy Notes

Google may require OAuth app verification for sensitive or restricted scopes.
Gmail scopes and broad Drive scopes can be more demanding than Calendar/Contacts.

Policy references:

- Google Drive API scopes:
  https://developers.google.com/workspace/drive/api/guides/api-specific-auth
- Gmail API scopes:
  https://developers.google.com/workspace/gmail/api/auth/scopes
- OAuth app verification:
  https://support.google.com/cloud/answer/13463073
- Google API Services User Data Policy:
  https://developers.google.com/terms/api-services-user-data-policy

Product implication:

- Build and test each scope-backed feature before requesting app verification.
- Keep a clear privacy policy and permission explanation page.
- Request only scopes that are active in the product.

## Implementation Phases

### Phase 1: Connected Apps UI

Goal:

- Add an "Apps conectadas" entry point.
- Show Google Workspace card.
- Show connection status using `/api/v1/integrations/google/status`.
- Let user start the existing Google integration flow.

Exit criteria:

- User can see whether Google is connected.
- User can start OAuth.
- Callback updates the UI with connected/error status.

Implementation status:

- Started on 2026-05-28.
- Web and desktop now expose "Apps conectadas" in the sidebar footer.
- The panel shows Google Workspace status, current Calendar/Contacts scopes,
  and planned Drive/Gmail scopes.
- Web uses the existing `/api/v1/integrations/google/status` and
  `/api/v1/integrations/google/start` endpoints directly.
- Desktop uses native commands that call the same backend endpoints with the
  securely stored desktop session token.

### Phase 2: Drive Search

Goal:

- Add Drive metadata scope.
- Add endpoint to search/list Drive files.
- Add `search_google_drive_files` tool.

Exit criteria:

- ARI can answer: "Busca en mi Drive el contrato de X."
- ARI returns file names, types, modified dates, and links.
- No file content is read yet.

### Phase 3: Drive File Reading

Goal:

- Add read capability for user-selected files.
- Support Google Docs export to text where possible.
- Support PDF/text extraction where practical.

Exit criteria:

- ARI can summarize a selected Drive document.
- ARI clearly states which file it is reading.
- Summary appears in chat Markdown history.

### Phase 4: Gmail Read

Goal:

- Add Gmail readonly scope.
- Add search/list/read endpoints.
- Add `search_gmail_messages` and `read_gmail_thread` tools.

Exit criteria:

- ARI can find emails by sender, subject, date, or query.
- ARI can summarize a selected email thread.
- ARI does not expose email content unless the authenticated user requested it.

### Phase 5: Gmail Drafts

Goal:

- Add Gmail compose scope.
- Add endpoint to create draft replies.
- Add `create_gmail_draft` tool.

Exit criteria:

- ARI can prepare a draft response.
- User can review it before sending.
- Draft creation is logged/audited.

### Phase 6: Gmail Send

Goal:

- Add Gmail send scope.
- Add `send_gmail_message` tool with high risk.
- Require explicit user confirmation.

Exit criteria:

- ARI never sends without confirmation.
- Confirmation displays recipient, subject, body, and attachments.
- Send result is audited.

## Open Questions

- Should "Connect Google" initially connect Calendar/Contacts only, or include
  Drive metadata too?
- Should Drive file reading require a per-file confirmation?
- Should Gmail send be allowed in MVP, or should MVP stop at drafts?
- Do we want Google Picker for selecting Drive files?
- Should mobile expose connected apps in the first version, or web/desktop first?

## Recommended First Build

Start with:

1. Connected Apps UI.
2. Google status and reconnect UX.
3. Drive metadata search.
4. Chat status: `ARI esta buscando en Drive`.
5. Clear "needs permission" response when Drive is not connected.

Delay:

- Gmail send.
- Broad Drive content reading.
- Automatic multi-app workflows.
