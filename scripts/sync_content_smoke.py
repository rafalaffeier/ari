from __future__ import annotations

import argparse
import hashlib
import time

import httpx


def register(base_url: str, email: str, password: str) -> dict:
    response = httpx.post(
        f"{base_url}/auth/register",
        json={"email": email, "password": password},
        timeout=10,
    )
    print("REGISTER", response.status_code)
    response.raise_for_status()
    return response.json()


def upload(base_url: str, workspace_id: str, token: str, path: str, content: bytes, base_version: int | None = None) -> dict:
    params: dict[str, str | int] = {"path": path}
    if base_version is not None:
        params["base_version"] = base_version
    response = httpx.put(
        f"{base_url}/sync/{workspace_id}/files/content",
        params=params,
        content=content,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/octet-stream",
            "X-Encryption-Algorithm": "AES-256-GCM",
            "X-Encryption-Key-Id": "local-smoke-workspace-key-v1",
            "X-Encryption-Nonce": "abc123456789",
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
    parser = argparse.ArgumentParser(description="Smoke test Phase 3 Markdown sync content upload/download.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000/api/v1")
    parser.add_argument("--password", default="secret12345")
    args = parser.parse_args()

    suffix = str(int(time.time()))
    auth = register(args.base_url, f"sync-content-{suffix}@example.com", args.password)
    token = auth["access_token"]
    workspace_id = auth["default_workspace_id"]
    path = "journal/2026/05/2026-05-23.md"

    content_v1 = b"# Sync smoke\n\n- Version one from desktop.\n"
    uploaded_v1 = upload(args.base_url, workspace_id, token, path, content_v1)
    if uploaded_v1["version"] != 1:
        raise SystemExit(f"Expected version 1, got {uploaded_v1['version']}")
    if uploaded_v1["checksum_sha256"] != hashlib.sha256(content_v1).hexdigest():
        raise SystemExit("Upload v1 checksum mismatch")

    downloaded_v1 = download(args.base_url, workspace_id, token, path)
    if downloaded_v1.content != content_v1:
        raise SystemExit("Downloaded v1 content mismatch")
    if downloaded_v1.headers.get("x-file-version") != "1":
        raise SystemExit("Downloaded v1 version header mismatch")

    content_v2 = b"# Sync smoke\n\n- Version two from desktop.\n"
    uploaded_v2 = upload(args.base_url, workspace_id, token, path, content_v2, base_version=1)
    if uploaded_v2["version"] != 2:
        raise SystemExit(f"Expected version 2, got {uploaded_v2['version']}")

    downloaded_v2 = download(args.base_url, workspace_id, token, path)
    if downloaded_v2.content != content_v2:
        raise SystemExit("Downloaded v2 content mismatch")

    conflict_content = b"# Sync smoke\n\n- Conflicting edit from another client.\n"
    conflict = upload(args.base_url, workspace_id, token, path, conflict_content, base_version=1)["conflict"]
    conflict_path = conflict["conflict_path"]
    if conflict["current_version"] != 2:
        raise SystemExit(f"Expected current version 2 in conflict, got {conflict['current_version']}")

    downloaded_conflict = download(args.base_url, workspace_id, token, conflict_path)
    if downloaded_conflict.content != conflict_content:
        raise SystemExit("Downloaded conflict content mismatch")

    files_response = httpx.get(
        f"{args.base_url}/sync/{workspace_id}/files",
        params={"prefix": "journal/2026/05"},
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )
    print("LIST_FILES", files_response.status_code)
    files_response.raise_for_status()
    paths = {item["path"] for item in files_response.json()}
    if path not in paths or conflict_path not in paths:
        raise SystemExit(f"Expected original and conflict paths in file list, got {paths}")

    events_response = httpx.get(
        f"{args.base_url}/sync/{workspace_id}/events",
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )
    print("LIST_EVENTS", events_response.status_code)
    events_response.raise_for_status()
    event_types = [event["event_type"] for event in events_response.json()]
    if "file_content.conflict" not in event_types:
        raise SystemExit(f"Expected conflict event, got {event_types}")

    print("SYNC_CONTENT_SMOKE_OK")


if __name__ == "__main__":
    main()
