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

## Delivery Checklist

Use this checklist as the working control board. A task is not closed until web,
desktop, mobile app, and mobile responsive behavior are accounted for.

### Checklist Workflow Rule

For every new feature or product change:

- [ ] Add or update the checklist before implementation starts.
- [ ] Define what "done" means in user-facing terms.
- [ ] Split the work by surface: web, desktop, mobile app, and mobile responsive.
- [ ] Track backend/API, UI, tests, deploy, and documentation separately.
- [ ] Update checklist status before committing.
- [ ] Record any known limitation or blocked item explicitly.
- [ ] Do not mark the task complete if one platform is missing unless the
  limitation is written down and accepted.

### Rule for Every UI Feature

- [ ] Web updated.
- [ ] Desktop updated.
- [ ] Mobile app updated.
- [ ] Mobile web/responsive checked.
- [ ] Production deploy checked when the feature affects web.
- [ ] Tests or type checks run for touched surfaces.
- [ ] Commit created with the completed scope.

### Connected Apps Entry and Google Connection

Definition of done:

- User can open "Apps conectadas" from web, desktop, and mobile app.
- Google Workspace status is visible.
- User can start Google OAuth from each surface.
- After authorization, ARI can refresh and show connected/error status.
- Calendar and Contacts show as active when their scopes are present.
- Drive and Gmail show as planned/not active until their phases are implemented.

Current status:

- [x] Plan document created and linked from `docs/README.md`.
- [x] Web: "Apps conectadas" entry added.
- [x] Web: Google Workspace panel added.
- [x] Web: status endpoint connected.
- [x] Web: start OAuth flow connected.
- [x] Web: callback query state handled.
- [x] Desktop: "Apps conectadas" entry added.
- [x] Desktop: Google Workspace panel added.
- [x] Desktop: native status/start integration commands added.
- [x] Desktop: opens browser for Google authorization.
- [x] Mobile web/responsive: panel has responsive layout rules.
- [x] Mobile app: "Apps conectadas" entry added in `mobile/App.tsx`.
- [x] Mobile app: Google Workspace panel/bottom sheet added.
- [x] Mobile app: integration status API added.
- [x] Mobile app: start OAuth API added.
- [x] Mobile app: `Linking.openURL(...)` connection flow added.
- [x] Mobile app: refresh status after browser authorization.
- [x] Mobile app: typecheck run.
- [x] Web deployed to production.
- [x] Production `/ready` checked after deploy.
- [ ] End-to-end OAuth smoke checked with a real account.

### Drive Search Phase

Definition of done:

- ARI can search Google Drive file metadata after the user connects/updates the
  required scope.
- ARI returns file name, type, modified date, and link/reference.
- ARI does not read file content in this phase.

Checklist:

- [ ] Add/request `drive.metadata.readonly` scope.
- [ ] Add backend Drive service.
- [ ] Add Drive search/list endpoint.
- [ ] Add `search_google_drive_files` tool.
- [ ] Add "needs permission" response when Drive scope is missing.
- [ ] Add chat status: `ARI esta buscando en Drive`.
- [ ] Add tests for connected/missing-scope/error cases.
- [ ] Update web, desktop, mobile app, and mobile responsive UI states.

### Gmail Phase

Definition of done:

- ARI can search/read emails only after explicit Gmail permission.
- Draft/send are separated.
- Sending email always requires explicit confirmation.

Checklist:

- [ ] Add/request Gmail readonly scope only when Gmail read is implemented.
- [ ] Add Gmail search/read endpoints.
- [ ] Add `search_gmail_messages` and `read_gmail_thread` tools.
- [ ] Add Gmail draft endpoint/tool.
- [ ] Add Gmail send endpoint/tool.
- [ ] Add high-risk confirmation flow for send.
- [ ] Add audit event for send/draft actions.
- [ ] Update web, desktop, mobile app, and mobile responsive UI states.

## ARI Product Backlog

This backlog captures product/UX ideas that should guide implementation. Keep it
separate from low-level tasks so ARI grows as a coherent assistant, not just as a
set of endpoints.

### Foundation: Cross-Platform Quality

These rules apply to every meaningful product change:

- [ ] Design starts from the desktop UI reference.
- [ ] Web matches desktop visually and behaviorally.
- [ ] Mobile app receives the same capability, adapted to native mobile layout.
- [ ] Mobile web/responsive behavior is checked.
- [ ] Login/session behavior is not bypassed.
- [ ] User history continues loading by authenticated user.
- [ ] Chats, summaries, and memory stay in Markdown/text files.
- [ ] PostgreSQL remains limited to user/auth/integration/metadata.
- [ ] No secrets or raw tokens appear in logs, chat, screenshots, or commits.

### Trust and Permission UX

Goal:

- The user should understand exactly what ARI can access, why it needs access,
  and how to change that access.

Checklist:

- [ ] Add an ideal "Trust and permissions" interface concept.
- [ ] Explain what each connected app permission enables.
- [ ] Show connected, disconnected, expired, and error states.
- [ ] Add a reconnect action.
- [ ] Add a future disconnect action.
- [ ] Explain that ARI's chat/memory history remains in Markdown/text files.
- [ ] Request Drive/Gmail permissions only when the user asks for a relevant task.
- [ ] Show "needs permission" prompts in chat when ARI cannot continue without access.

### ARI Working Overlay

Goal:

- When ARI is thinking or running a tool, the user should immediately feel that
  the system is alive and busy. The interface should block conflicting actions
  until ARI finishes.

Design direction:

- Full-screen overlay above the interface.
- Soft futuristic fade-in/fade-out pulse.
- Subtle color wash/shadow that breathes in and out.
- ARI status label changes by task, for example:
  - `ARI esta pensando`
  - `ARI esta buscando vuelos`
  - `ARI esta revisando tu calendario`
  - `ARI esta buscando en Drive`
  - `ARI esta leyendo el documento`
  - `ARI esta preparando un borrador`
- Overlay disappears when ARI returns a result or an error.
- Input, microphone, and external action buttons are disabled while active.

Checklist:

- [ ] Define desktop visual design for the overlay.
- [ ] Implement in web.
- [ ] Implement in desktop.
- [ ] Implement in mobile app.
- [ ] Check mobile web/responsive behavior.
- [ ] Connect to chat send, voice, flight search, Google actions, Drive actions,
  Gmail actions, and future long-running tools.
- [ ] Add timeout/error state: `La accion tardo demasiado. Puedes intentar otra vez.`
- [ ] Verify that the overlay always clears after success, error, or cancellation.

### Sensitive Actions

Goal:

- ARI must never perform external real-world actions silently.

Checklist:

- [ ] Require confirmation before sending any email.
- [ ] Require confirmation before creating important calendar events.
- [ ] Show email preview before sending: recipient, subject, body, and attachments.
- [ ] Decide later whether email preview should be iframe, native panel, or
  structured preview card.
- [ ] Add audit log for email send, draft creation, and important calendar events.
- [ ] Add a "never execute silently" rule to tool execution.
- [ ] Add tests for denied confirmation and approved confirmation paths.

### Google Improvements by Phase

Calendar:

- [ ] Read upcoming events.
- [ ] Check availability.
- [ ] Create event after confirmation when important.
- [ ] Modify/cancel event only after explicit confirmation.

Contacts:

- [ ] Search people by name/email/phone.
- [ ] Help select recipients for email/calendar tasks.

Drive:

- [ ] Search metadata first.
- [ ] Let the user select a file.
- [ ] Read selected files only after the relevant scope and clear user intent.
- [ ] State which file ARI is reading before summarizing.

Gmail:

- [ ] Search messages.
- [ ] Summarize selected threads.
- [ ] Prepare draft replies.
- [ ] Send only after explicit confirmation.

### Visible Memory

Goal:

- The user should be able to inspect and manage what ARI remembers.

Checklist:

- [ ] Add "What ARI remembers" panel.
- [ ] Show memory files/text entries by user/workspace.
- [ ] Let the user search memory.
- [ ] Let the user delete or edit selected memory entries.
- [ ] Let the user export memory.
- [ ] Show source hints in answers: memory, Drive, email, calendar, or tool result.

### Debug and Operations Backlog

Use this when it helps diagnose real issues without cluttering the product too
early.

- [ ] Add tool health/status indicators.
- [ ] Add visible retry action for failed tools.
- [ ] Add non-secret error logs for Google integration.
- [ ] Add timeout messages for long-running tools.
- [ ] Add OAuth smoke test checklist with a controlled account.
- [ ] Add production runbook notes when a new external integration ships.

### Suggested Work Order

1. Finish mobile app parity for Connected Apps.
2. Build the ARI Working Overlay across web, desktop, and mobile.
3. Add sensitive-action confirmation foundation.
4. Add Drive metadata search.
5. Add visible memory panel.
6. Add Gmail read/draft/send in separate phases.

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
- Mobile app uses the same backend endpoints from `mobile/src/services/api.ts`
  and opens Google authorization with React Native `Linking`.

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
