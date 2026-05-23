# Encryption Contract

Phase 4 makes memory sync client-side encrypted. The backend must never receive readable Markdown for synced memory content.

For now, the server stores the full synchronized memory copy as ciphertext. Local devices may also keep their own Markdown cache, but retention, pruning, and server-space optimization are deferred until the product has enough real usage data.

## Responsibilities

| Component | Responsibility |
| --- | --- |
| Desktop/Mobile client | Encrypt Markdown before upload and decrypt downloaded ciphertext locally. |
| Backend API | Authorize access, validate envelope metadata, store ciphertext bytes, and track versions/events. |
| PostgreSQL | Store only sync metadata, `storage_key`, ciphertext checksum/size, and non-secret envelope metadata. |
| Sync storage | Store ciphertext bytes. |

## Content Upload

Clients upload encrypted bytes to:

```text
PUT /api/v1/sync/{workspace_id}/files/content?path={workspace-relative-markdown-path}
```

Request requirements:

- `Content-Type: application/octet-stream`
- `X-Encryption-Algorithm: AES-256-GCM`
- `X-Encryption-Key-Id: <client key id>`
- `X-Encryption-Nonce: <base64url nonce>`
- `X-Encryption-Envelope-Version: 1`
- Body is ciphertext, not Markdown plaintext.

The `checksum_sha256` stored in `file_versions` is the checksum of the ciphertext bytes.

## Content Download

Clients download encrypted bytes from:

```text
GET /api/v1/sync/{workspace_id}/files/content?path={workspace-relative-markdown-path}
```

The response body is ciphertext with:

- `Content-Type: application/octet-stream`
- `X-Encryption-Algorithm`
- `X-Encryption-Key-Id`
- `X-Encryption-Nonce`
- `X-Encryption-Envelope-Version`
- `X-Checksum-SHA256`
- `X-File-Version`
- `X-Size-Bytes`

Only the client should use the appropriate local key to decrypt the body back into Markdown.

## Phase 4 Boundary

Done in this phase:

- Sync content is accepted and returned as ciphertext only.
- Envelope metadata is stored separately from file bytes.
- Desktop can create, serialize, store, encrypt with, and decrypt with a workspace-scoped key.
- The backend stores device-specific and recovery-specific workspace key wraps as opaque ciphertext.
- Revoked devices cannot read stored workspace key wraps.
- Synced filenames are constrained to metadata-safe structural paths.

Deferred:

- User-facing key rotation UX.
- Real inter-device wrapping UX around the backend `workspace_key_wraps` contract.
- Recovery kit creation and restore UX around the backend `workspace_recovery_wraps` contract.
- Object-storage signed URLs. Current Phase 4 storage uses the authenticated API directly; signed URLs belong with object storage in Phase 7.
- Retention, pruning, local-only tiers, and server-space optimization.

## Workspace Key Wraps

Clients publish an opaque, device-specific wrapped workspace key to:

```text
POST /api/v1/sync/{workspace_id}/keys/wraps
```

Request body:

```json
{
  "device_id": "authorized-device-uuid",
  "key_id": "workspace-key-v1",
  "wrapping_algorithm": "X25519-AES-256-GCM",
  "wrapped_key": "opaque-client-produced-ciphertext"
}
```

The backend stores `wrapped_key` as opaque ciphertext. It does not unwrap, derive, or validate the underlying workspace key.

Devices retrieve their active wraps from:

```text
GET /api/v1/sync/{workspace_id}/keys/wraps?device_id={device_id}
```

If the device is revoked, this endpoint returns `403`.

## Recovery Wraps

Clients may publish an opaque, recovery-phrase-wrapped workspace key to:

```text
POST /api/v1/sync/{workspace_id}/keys/recovery
```

Request body:

```json
{
  "key_id": "workspace-key-v1",
  "wrapping_algorithm": "RECOVERY-PHRASE-AES-256-GCM",
  "wrapped_key": "opaque-client-produced-ciphertext",
  "recovery_hint": "printed recovery kit"
}
```

The recovery phrase, seed, password, or mnemonic must never be sent to the backend. `recovery_hint` must not contain secret material.

Authorized clients retrieve recovery wraps from:

```text
GET /api/v1/sync/{workspace_id}/keys/recovery
```

## Metadata-Safe Paths

Synced memory paths must avoid names of people, projects, organizations, medical topics, financial topics, or other sensitive labels. The backend accepts only structural paths:

- `journal/YYYY/MM/YYYY-MM-DD.md`
- `summaries/YYYY-Www.md`
- `summaries/YYYY-MM.md`
- `entities/projects.md`
- `entities/people.md`
- `entities/preferences.md`

Conflict copies use the same structural path plus `.conflict-{id}.md`.

## Desktop Client Status

The desktop crate includes initial client-side AES-256-GCM support:

- `WorkspaceKey::generate()`
- `WorkspaceKey::to_base64()` / `WorkspaceKey::from_base64()`
- `WorkspaceKey::encrypt_markdown()`
- `WorkspaceKey::decrypt_markdown()`
- `MemoryClient::upload_encrypted_markdown()`
- `MemoryClient::download_encrypted_markdown()`
- `MemoryClient::upsert_workspace_key_wrap()`
- `MemoryClient::list_workspace_key_wraps()`
- `MemoryClient::upsert_workspace_recovery_wrap()`
- `MemoryClient::list_workspace_recovery_wraps()`
- Tauri `ensure_workspace_key` and `clear_workspace_key` commands backed by OS secure storage

The key is created on auth persistence and stored under a workspace-scoped Keychain entry. Real inter-device wrapping (`X25519-AES-256-GCM`) and recovery-kit UX remain pending product flows over the backend contracts above.
