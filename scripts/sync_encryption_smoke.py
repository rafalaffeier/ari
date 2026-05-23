from __future__ import annotations

import argparse
import base64
import hashlib
import os
import time

import httpx
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def register(base_url: str, email: str, password: str) -> dict:
    response = httpx.post(
        f"{base_url}/auth/register",
        json={"email": email, "password": password},
        timeout=10,
    )
    print("REGISTER", response.status_code)
    response.raise_for_status()
    return response.json()


def encrypt_markdown(key: bytes, plaintext: bytes, path: str) -> tuple[bytes, str]:
    nonce = os.urandom(12)
    ciphertext = AESGCM(key).encrypt(nonce, plaintext, path.encode("utf-8"))
    return ciphertext, base64.urlsafe_b64encode(nonce).decode("ascii").rstrip("=")


def decrypt_markdown(key: bytes, ciphertext: bytes, path: str, nonce: str) -> bytes:
    padded_nonce = nonce + "=" * (-len(nonce) % 4)
    nonce_bytes = base64.urlsafe_b64decode(padded_nonce)
    return AESGCM(key).decrypt(nonce_bytes, ciphertext, path.encode("utf-8"))


def upload(
    base_url: str,
    workspace_id: str,
    token: str,
    path: str,
    ciphertext: bytes,
    nonce: str,
    base_version: int | None = None,
) -> dict:
    params: dict[str, str | int] = {"path": path}
    if base_version is not None:
        params["base_version"] = base_version
    response = httpx.put(
        f"{base_url}/sync/{workspace_id}/files/content",
        params=params,
        content=ciphertext,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/octet-stream",
            "X-Encryption-Algorithm": "AES-256-GCM",
            "X-Encryption-Key-Id": "local-smoke-workspace-key-v1",
            "X-Encryption-Nonce": nonce,
            "X-Encryption-Envelope-Version": "1",
        },
        timeout=10,
    )
    print("UPLOAD", path, response.status_code)
    if response.status_code == 409:
        return {"conflict": response.json()["detail"]}
    response.raise_for_status()
    return response.json()


def download(base_url: str, workspace_id: str, token: str, path: str) -> httpx.Response:
    response = httpx.get(
        f"{base_url}/sync/{workspace_id}/files/content",
        params={"path": path},
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )
    print("DOWNLOAD", path, response.status_code)
    response.raise_for_status()
    return response


def main() -> None:
    parser = argparse.ArgumentParser(description="Smoke test Phase 4 encrypted Markdown sync.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000/api/v1")
    parser.add_argument("--password", default="secret12345")
    args = parser.parse_args()

    suffix = str(int(time.time()))
    auth = register(args.base_url, f"sync-encryption-{suffix}@example.com", args.password)
    token = auth["access_token"]
    workspace_id = auth["default_workspace_id"]
    path = "journal/2026/05/2026-05-23.md"
    key = AESGCM.generate_key(bit_length=256)

    plaintext_v1 = b"# Encrypted sync smoke\n\n- Version one stays client-readable only.\n"
    ciphertext_v1, nonce_v1 = encrypt_markdown(key, plaintext_v1, path)
    uploaded_v1 = upload(args.base_url, workspace_id, token, path, ciphertext_v1, nonce_v1)
    if uploaded_v1["checksum_sha256"] != hashlib.sha256(ciphertext_v1).hexdigest():
        raise SystemExit("Upload v1 ciphertext checksum mismatch")
    if uploaded_v1["encryption_metadata"]["algorithm"] != "AES-256-GCM":
        raise SystemExit("Upload v1 encryption metadata mismatch")

    downloaded_v1 = download(args.base_url, workspace_id, token, path)
    if downloaded_v1.content == plaintext_v1:
        raise SystemExit("Server returned plaintext")
    if decrypt_markdown(key, downloaded_v1.content, path, downloaded_v1.headers["x-encryption-nonce"]) != plaintext_v1:
        raise SystemExit("Downloaded v1 decrypt mismatch")

    plaintext_v2 = b"# Encrypted sync smoke\n\n- Version two also stays encrypted at rest.\n"
    ciphertext_v2, nonce_v2 = encrypt_markdown(key, plaintext_v2, path)
    uploaded_v2 = upload(args.base_url, workspace_id, token, path, ciphertext_v2, nonce_v2, base_version=1)
    if uploaded_v2["version"] != 2:
        raise SystemExit(f"Expected version 2, got {uploaded_v2['version']}")

    conflict_plaintext = b"# Encrypted sync smoke\n\n- Stale encrypted edit preserved as conflict.\n"
    conflict_ciphertext, conflict_nonce = encrypt_markdown(key, conflict_plaintext, path)
    conflict = upload(args.base_url, workspace_id, token, path, conflict_ciphertext, conflict_nonce, base_version=1)["conflict"]
    conflict_path = conflict["conflict_path"]
    conflict_download = download(args.base_url, workspace_id, token, conflict_path)
    if conflict_download.content == conflict_plaintext:
        raise SystemExit("Server returned conflict plaintext")
    if (
        decrypt_markdown(key, conflict_download.content, path, conflict_download.headers["x-encryption-nonce"])
        != conflict_plaintext
    ):
        raise SystemExit("Downloaded conflict decrypt mismatch")

    print("SYNC_ENCRYPTION_SMOKE_OK")


if __name__ == "__main__":
    main()
