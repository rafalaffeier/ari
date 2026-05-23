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
    parser = argparse.ArgumentParser(description="Smoke test Phase 4 recovery-wrapped workspace key flow.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000/api/v1")
    parser.add_argument("--password", default="secret12345")
    args = parser.parse_args()

    suffix = str(int(time.time()))
    auth = register(args.base_url, f"sync-recovery-{suffix}@example.com", args.password)
    token = auth["access_token"]
    workspace_id = auth["default_workspace_id"]
    headers = {"Authorization": f"Bearer {token}"}
    wrapped_key = base64.urlsafe_b64encode(os.urandom(80)).decode("ascii").rstrip("=")

    create_response = httpx.post(
        f"{args.base_url}/sync/{workspace_id}/keys/recovery",
        json={
            "key_id": "workspace-key-v1",
            "wrapping_algorithm": "RECOVERY-PHRASE-AES-256-GCM",
            "wrapped_key": wrapped_key,
            "recovery_hint": "printed recovery kit",
        },
        headers=headers,
        timeout=10,
    )
    print("UPSERT_RECOVERY", create_response.status_code)
    create_response.raise_for_status()
    created = create_response.json()
    if created["wrapped_key"] != wrapped_key:
        raise SystemExit("Stored recovery wrapped key mismatch")

    list_response = httpx.get(
        f"{args.base_url}/sync/{workspace_id}/keys/recovery",
        headers=headers,
        timeout=10,
    )
    print("LIST_RECOVERY", list_response.status_code)
    list_response.raise_for_status()
    wraps = list_response.json()
    if len(wraps) != 1 or wraps[0]["wrapping_algorithm"] != "RECOVERY-PHRASE-AES-256-GCM":
        raise SystemExit(f"Unexpected recovery wraps: {wraps}")

    bad_hint_response = httpx.post(
        f"{args.base_url}/sync/{workspace_id}/keys/recovery",
        json={
            "key_id": "workspace-key-v2",
            "wrapping_algorithm": "RECOVERY-PHRASE-AES-256-GCM",
            "wrapped_key": wrapped_key,
            "recovery_hint": "my seed phrase is abc",
        },
        headers=headers,
        timeout=10,
    )
    print("BAD_HINT_REJECTED", bad_hint_response.status_code)
    if bad_hint_response.status_code != 400:
        raise SystemExit(f"Expected bad hint 400, got {bad_hint_response.status_code}: {bad_hint_response.text}")

    print("SYNC_RECOVERY_SMOKE_OK")


if __name__ == "__main__":
    main()
