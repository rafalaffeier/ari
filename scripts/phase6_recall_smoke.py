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
    print("REGISTER", response.status_code)
    response.raise_for_status()
    return response.json()


def add_entry(base_url: str, workspace_id: str, token: str, day: str, section: str, text: str) -> None:
    response = httpx.post(
        f"{base_url}/memory/{workspace_id}/journal/{day}/entries",
        json={"section": section, "text": text, "timestamp": f"{day}T09:30:00Z"},
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )
    print("ADD_ENTRY", day, section, response.status_code)
    response.raise_for_status()


def recall(base_url: str, workspace_id: str, token: str, message: str, limit: int = 5) -> dict:
    response = httpx.post(
        f"{base_url}/messages/{workspace_id}/recall",
        json={"message": message, "limit": limit},
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )
    print("RECALL", response.status_code, message)
    response.raise_for_status()
    return response.json()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def main() -> None:
    parser = argparse.ArgumentParser(description="Smoke test Phase 6 memory recall over the authenticated backend API.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000/api/v1")
    parser.add_argument("--password", default="secret12345")
    args = parser.parse_args()

    suffix = str(int(time.time()))
    auth = register(args.base_url, f"phase6-recall-{suffix}@example.com", args.password)
    token = auth["access_token"]
    workspace_id = auth["default_workspace_id"]

    add_entry(args.base_url, workspace_id, token, "2026-05-21", "tasks", "Started recent recall smoke coverage.")
    add_entry(args.base_url, workspace_id, token, "2026-05-23", "decisions", "Launch pricing stays simple for the MVP.")

    by_date = recall(args.base_url, workspace_id, token, "What happened on 2026-05-23?")
    require(by_date["memory_results"], "Expected date recall results")
    require(by_date["memory_results"][0]["date"] == "2026-05-23", f"Unexpected date recall: {by_date}")
    require("journal/2026/05/2026-05-23.md" in by_date["context"], "Date recall did not cite journal path")
    require("Launch pricing stays simple" in by_date["context"], "Date recall missing expected entry")

    by_topic = recall(args.base_url, workspace_id, token, "When did we discuss launch pricing?")
    require(by_topic["memory_results"], "Expected topic recall results")
    require(by_topic["memory_results"][0]["reason"] == "text-search", f"Expected text-search result: {by_topic}")
    require("Launch pricing stays simple" in by_topic["context"], "Topic recall missing expected entry")

    recent = recall(args.base_url, workspace_id, token, "What happened in the last 3 days?", limit=5)
    dates = {item["date"] for item in recent["memory_results"]}
    require({"2026-05-21", "2026-05-23"}.issubset(dates), f"Recent recall missing expected dates: {recent}")
    require("recent-journal" in recent["context"], "Recent recall did not use recent-journal sources")

    missing = recall(args.base_url, workspace_id, token, "When did we discuss quantum bananas?", limit=5)
    require(missing["memory_results"] == [], f"Expected no missing recall results: {missing}")
    require("no matching memory sources" in missing["context"], "Missing recall did not include no-source guardrail")
    require("do not invent" in missing["context"], "Missing recall did not include no-invention guardrail")

    print("PHASE6_RECALL_SMOKE_OK")


if __name__ == "__main__":
    main()
