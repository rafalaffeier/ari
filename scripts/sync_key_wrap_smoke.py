from __future__ import annotations

import argparse
import base64
import os
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Smoke test Phase 4 workspace key wraps and device revocation.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000/api/v1")
    parser.add_argument("--password", default="secret12345")
    args = parser.parse_args()

    suffix = str(int(time.time()))
    auth = register(args.base_url, f"sync-key-wrap-{suffix}@example.com", args.password)
    token = auth["access_token"]
    workspace_id = auth["default_workspace_id"]
    headers = {"Authorization": f"Bearer {token}"}

    device_response = httpx.post(
        f"{args.base_url}/devices/register",
        json={"device_name": "Phase4 smoke device", "platform": "macos", "workspace_id": workspace_id},
        headers=headers,
        timeout=10,
    )
    print("REGISTER_DEVICE", device_response.status_code)
    device_response.raise_for_status()
    device_id = device_response.json()["device_id"]

    wrapped_key = base64.urlsafe_b64encode(os.urandom(64)).decode("ascii").rstrip("=")
    wrap_response = httpx.post(
        f"{args.base_url}/sync/{workspace_id}/keys/wraps",
        json={
            "device_id": device_id,
            "key_id": "workspace-key-v1",
            "wrapping_algorithm": "LOCAL-TEST-AES-256-GCM",
            "wrapped_key": wrapped_key,
        },
        headers=headers,
        timeout=10,
    )
    print("UPSERT_WRAP", wrap_response.status_code)
    wrap_response.raise_for_status()
    wrap = wrap_response.json()
    if wrap["wrapped_key"] != wrapped_key:
        raise SystemExit("Stored wrapped key mismatch")

    list_response = httpx.get(
        f"{args.base_url}/sync/{workspace_id}/keys/wraps",
        params={"device_id": device_id},
        headers=headers,
        timeout=10,
    )
    print("LIST_WRAPS", list_response.status_code)
    list_response.raise_for_status()
    wraps = list_response.json()
    if len(wraps) != 1 or wraps[0]["key_id"] != "workspace-key-v1":
        raise SystemExit(f"Unexpected key wraps: {wraps}")

    revoke_response = httpx.post(
        f"{args.base_url}/devices/{device_id}/revoke",
        headers=headers,
        timeout=10,
    )
    print("REVOKE_DEVICE", revoke_response.status_code)
    if revoke_response.status_code != 204:
        raise SystemExit(f"Expected revoke 204, got {revoke_response.status_code}: {revoke_response.text}")

    revoked_list_response = httpx.get(
        f"{args.base_url}/sync/{workspace_id}/keys/wraps",
        params={"device_id": device_id},
        headers=headers,
        timeout=10,
    )
    print("LIST_WRAPS_REVOKED", revoked_list_response.status_code)
    if revoked_list_response.status_code != 403:
        raise SystemExit(
            f"Expected revoked device key access 403, got {revoked_list_response.status_code}: "
            f"{revoked_list_response.text}"
        )

    print("SYNC_KEY_WRAP_SMOKE_OK")


if __name__ == "__main__":
    main()
