from __future__ import annotations

import argparse
import time

import httpx


def register(base_url: str, email: str, password: str) -> dict:
    response = httpx.post(
        f"{base_url}/auth/register",
        json={"email": email, "password": password},
        timeout=10,
    )
    print("REGISTER", email, response.status_code)
    response.raise_for_status()
    return response.json()


def main() -> None:
    parser = argparse.ArgumentParser(description="Smoke test Phase 1 auth/workspace/memory isolation.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000/api/v1")
    parser.add_argument("--password", default="secret12345")
    args = parser.parse_args()

    suffix = str(int(time.time()))
    user_a = register(args.base_url, f"phase1-user-a-{suffix}@example.com", args.password)
    user_b = register(args.base_url, f"phase1-user-b-{suffix}@example.com", args.password)

    headers_a = {"Authorization": f"Bearer {user_a['access_token']}"}
    headers_b = {"Authorization": f"Bearer {user_b['access_token']}"}
    workspace_a = user_a["default_workspace_id"]

    write_response = httpx.post(
        f"{args.base_url}/memory/{workspace_a}/journal/2026-05-11/entries",
        json={
            "section": "decisions",
            "text": "Phase 1 auth memory smoke passed.",
            "timestamp": "2026-05-11T19:15:00Z",
        },
        headers=headers_a,
        timeout=10,
    )
    print("WRITE_A", write_response.status_code)
    write_response.raise_for_status()

    read_response = httpx.get(
        f"{args.base_url}/memory/{workspace_a}/journal/2026-05-11/overview",
        headers=headers_a,
        timeout=10,
    )
    print("READ_A", read_response.status_code)
    read_response.raise_for_status()

    forbidden_response = httpx.get(
        f"{args.base_url}/memory/{workspace_a}/journal/2026-05-11/overview",
        headers=headers_b,
        timeout=10,
    )
    print("READ_B_FORBIDDEN", forbidden_response.status_code)
    if forbidden_response.status_code != 403:
        raise SystemExit(f"Expected 403, got {forbidden_response.status_code}: {forbidden_response.text}")

    print("PHASE1_SMOKE_OK")


if __name__ == "__main__":
    main()
