import tempfile
import unittest
import uuid

try:
    from fastapi.testclient import TestClient
except ModuleNotFoundError:
    TestClient = None

if TestClient is not None:
    from fastapi import Path

    from app.api.deps import require_workspace_access
    from app.core.config import settings
    from app.main import app
    from app.api.v1.endpoints import messages


WORKSPACE_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")


if TestClient is not None:
    async def workspace_access_override(workspace_id: uuid.UUID = Path(...)):
        return workspace_id


@unittest.skipIf(TestClient is None, "FastAPI dependencies are not installed")
class MemoryApiTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.original_memory_root = settings.MEMORY_ROOT
        settings.MEMORY_ROOT = self.tmp.name
        app.dependency_overrides[require_workspace_access] = workspace_access_override
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()
        settings.MEMORY_ROOT = self.original_memory_root
        self.tmp.cleanup()

    def test_append_read_overview_and_search(self):
        create_response = self.client.post(
            f"/api/v1/memory/{WORKSPACE_ID}/journal/2026-05-11/entries",
            json={"section": "tasks", "text": "Created API-level memory foundation.", "timestamp": "2026-05-11T09:30:00Z"},
        )
        self.assertEqual(create_response.status_code, 201)

        read_response = self.client.get(f"/api/v1/memory/{WORKSPACE_ID}/journal/2026-05-11")
        self.assertEqual(read_response.status_code, 200)
        self.assertIn("- 09:30 Created API-level memory foundation.", read_response.json()["content"])

        overview_response = self.client.get(f"/api/v1/memory/{WORKSPACE_ID}/journal/2026-05-11/overview")
        self.assertEqual(overview_response.status_code, 200)
        self.assertIn("Created API-level memory foundation.", overview_response.json()["sections"]["tasks"][0])

        search_response = self.client.get(f"/api/v1/memory/{WORKSPACE_ID}/search", params={"q": "API-level"})
        self.assertEqual(search_response.status_code, 200)
        self.assertEqual(len(search_response.json()), 1)

        timeline_response = self.client.get(f"/api/v1/memory/{WORKSPACE_ID}/timeline")
        self.assertEqual(timeline_response.status_code, 200)
        self.assertEqual(timeline_response.json()[0]["date"], "2026-05-11")
        self.assertEqual(timeline_response.json()[0]["entry_count"], 1)
        self.assertEqual(timeline_response.json()[0]["sections"]["tasks"], 1)

    def test_rejects_invalid_workspace_uuid(self):
        response = self.client.get("/api/v1/memory/bad.workspace/journal/2026-05-11")

        self.assertEqual(response.status_code, 422)

    def test_requires_auth_without_workspace_override(self):
        app.dependency_overrides.clear()
        response = self.client.get(f"/api/v1/memory/{WORKSPACE_ID}/journal/2026-05-11")

        self.assertEqual(response.status_code, 401)

    def test_chat_uses_openai_client_and_stores_transcript(self):
        original_api_key = settings.OPENAI_API_KEY
        original_complete_text = messages.complete_text
        user_message = "Remember that I prefer short replies and remind me to call Laura tomorrow"

        async def fake_complete_text(user_prompt: str, system_prompt: str):
            self.assertIn(f"User message:\n{user_message}", user_prompt)
            self.assertIn("Default to English", system_prompt)
            return "Launch plan noted."

        settings.OPENAI_API_KEY = "test-key"
        messages.complete_text = fake_complete_text
        try:
            response = self.client.post(
                f"/api/v1/messages/{WORKSPACE_ID}/chat",
                json={"message": user_message},
            )
        finally:
            settings.OPENAI_API_KEY = original_api_key
            messages.complete_text = original_complete_text

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["reply"], "Launch plan noted.")
        self.assertEqual(response.json()["stored_actions"], ["facts", "pending"])
        stored = self.client.get(f"/api/v1/memory/{WORKSPACE_ID}/journal/today")
        self.assertEqual(stored.status_code, 200)
        self.assertIn(f"User: {user_message}", stored.json()["content"])
        self.assertIn("ARI: Launch plan noted.", stored.json()["content"])
        self.assertIn(f"User memory: {user_message}", stored.json()["content"])
        self.assertIn(f"Follow-up/task: {user_message}", stored.json()["content"])

        recent = self.client.get(f"/api/v1/messages/{WORKSPACE_ID}/recent", params={"limit": 5})
        self.assertEqual(recent.status_code, 200)
        self.assertEqual(recent.json()[0]["title"], user_message)

        conversation_ref = recent.json()[0]
        conversation = self.client.get(
            f"/api/v1/messages/{WORKSPACE_ID}/conversation/{conversation_ref['date']}/{conversation_ref['line_number']}"
        )
        self.assertEqual(conversation.status_code, 200)
        self.assertEqual(conversation.json()["messages"][0], {"role": "user", "content": user_message})
        self.assertEqual(conversation.json()["messages"][1], {"role": "assistant", "content": "Launch plan noted."})

    def test_chat_requires_openai_api_key(self):
        original_api_key = settings.OPENAI_API_KEY
        settings.OPENAI_API_KEY = ""
        try:
            response = self.client.post(
                f"/api/v1/messages/{WORKSPACE_ID}/chat",
                json={"message": "Hello"},
            )
        finally:
            settings.OPENAI_API_KEY = original_api_key

        self.assertEqual(response.status_code, 503)

    def test_chat_recall_by_date_passes_cited_memory_context(self):
        self.client.post(
            f"/api/v1/memory/{WORKSPACE_ID}/journal/2026-05-11/entries",
            json={"section": "decisions", "text": "Keep Markdown as source of truth.", "timestamp": "2026-05-11T09:30:00Z"},
        )
        original_api_key = settings.OPENAI_API_KEY
        original_complete_text = messages.complete_text

        async def fake_complete_text(user_prompt: str, system_prompt: str):
            self.assertIn("journal/2026/05/2026-05-11.md", user_prompt)
            self.assertIn("Keep Markdown as source of truth.", user_prompt)
            self.assertIn("cite the source date or file:line", user_prompt)
            return "On 2026-05-11, we decided to keep Markdown as source of truth."

        settings.OPENAI_API_KEY = "test-key"
        messages.complete_text = fake_complete_text
        try:
            response = self.client.post(
                f"/api/v1/messages/{WORKSPACE_ID}/chat",
                json={"message": "What happened on 2026-05-11?"},
            )
        finally:
            settings.OPENAI_API_KEY = original_api_key
            messages.complete_text = original_complete_text

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["memory_results"][0]["date"], "2026-05-11")
        self.assertIn("Keep Markdown", response.json()["memory_results"][0]["line"])

    def test_recall_endpoint_returns_sources_without_openai(self):
        self.client.post(
            f"/api/v1/memory/{WORKSPACE_ID}/journal/2026-05-11/entries",
            json={"section": "tasks", "text": "Reviewed launch pricing.", "timestamp": "2026-05-11T09:30:00Z"},
        )

        response = self.client.post(
            f"/api/v1/messages/{WORKSPACE_ID}/recall",
            json={"message": "When did we discuss launch pricing?", "limit": 3},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["memory_results"][0]["date"], "2026-05-11")
        self.assertEqual(payload["memory_results"][0]["reason"], "text-search")
        self.assertIn("journal/2026/05/2026-05-11.md", payload["context"])

    def test_chat_empty_recall_context_warns_model_not_to_invent(self):
        original_api_key = settings.OPENAI_API_KEY
        original_complete_text = messages.complete_text

        async def fake_complete_text(user_prompt: str, system_prompt: str):
            self.assertIn("no matching memory sources were found", user_prompt)
            self.assertIn("do not invent dates", user_prompt)
            return "I do not have enough memory to answer that."

        settings.OPENAI_API_KEY = "test-key"
        messages.complete_text = fake_complete_text
        try:
            response = self.client.post(
                f"/api/v1/messages/{WORKSPACE_ID}/chat",
                json={"message": "When did we discuss launch pricing?"},
            )
        finally:
            settings.OPENAI_API_KEY = original_api_key
            messages.complete_text = original_complete_text

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["memory_results"], [])

    def test_orchestrate_handles_normal_conversation(self):
        original_api_key = settings.OPENAI_API_KEY
        original_complete = messages.complete

        async def fake_complete(user_prompt: str, system_prompt: str):
            self.assertIn("User message:\nhow are you?", user_prompt)
            self.assertIn("execution brain", system_prompt)
            return """
            {
              "mode": "reply",
              "reply": "I am here and ready to help.",
              "tool_name": null,
              "params": {},
              "missing": [],
              "requires_confirmation": false,
              "confidence": 0.96,
              "language": "en"
            }
            """

        settings.OPENAI_API_KEY = "test-key"
        messages.complete = fake_complete
        try:
            response = self.client.post(
                f"/api/v1/messages/{WORKSPACE_ID}/orchestrate",
                json={"message": "how are you?"},
            )
        finally:
            settings.OPENAI_API_KEY = original_api_key
            messages.complete = original_complete

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["mode"], "reply")
        self.assertEqual(payload["reply"], "I am here and ready to help.")
        self.assertIsNone(payload["tool_name"])

    def test_orchestrate_prepares_complete_calendar_action(self):
        original_api_key = settings.OPENAI_API_KEY
        original_complete = messages.complete
        user_message = "create a calendar event tomorrow at 9 in Trabajo called Test ARI"

        async def fake_complete(user_prompt: str, system_prompt: str):
            self.assertIn(f"User message:\n{user_message}", user_prompt)
            return """
            {
              "mode": "tool_confirmation",
              "reply": "I will create “Test ARI” in Trabajo tomorrow at 09:00 for 30 minutes. Confirm?",
              "tool_name": "create_calendar_event",
              "params": {
                "calendar": "Trabajo",
                "title": "Test ARI",
                "start": "2026-05-24T09:00:00",
                "end": "2026-05-24T09:30:00"
              },
              "missing": [],
              "requires_confirmation": true,
              "confidence": 0.98,
              "language": "en"
            }
            """

        settings.OPENAI_API_KEY = "test-key"
        messages.complete = fake_complete
        try:
            response = self.client.post(
                f"/api/v1/messages/{WORKSPACE_ID}/orchestrate",
                json={"message": user_message},
            )
        finally:
            settings.OPENAI_API_KEY = original_api_key
            messages.complete = original_complete

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["mode"], "tool_confirmation")
        self.assertEqual(payload["tool_name"], "create_calendar_event")
        self.assertEqual(payload["missing"], [])
        self.assertEqual(payload["params"]["title"], "Test ARI")
        self.assertEqual(payload["params"]["calendar"], "Trabajo")
        self.assertEqual(payload["params"]["start"], "2026-05-24T09:00:00")

    def test_orchestrate_does_not_fake_unconnected_travel_search(self):
        original_api_key = settings.OPENAI_API_KEY
        original_complete = messages.complete

        async def fake_complete(user_prompt: str, system_prompt: str):
            self.assertIn("Planned but not executable yet", user_prompt)
            return """
            {
              "mode": "tool_ready",
              "reply": "Buscando vuelos de Lisboa a Valencia para mañana.",
              "tool_name": "search_flights",
              "params": {
                "origin": "Lisboa",
                "destination": "Valencia",
                "departure_date": "2026-05-24"
              },
              "missing": [],
              "requires_confirmation": false,
              "confidence": 0.9,
              "language": "es"
            }
            """

        settings.OPENAI_API_KEY = "test-key"
        messages.complete = fake_complete
        try:
            response = self.client.post(
                f"/api/v1/messages/{WORKSPACE_ID}/orchestrate",
                json={"message": "buscame un viaje de Lisboa a Valencia para mañana"},
            )
        finally:
            settings.OPENAI_API_KEY = original_api_key
            messages.complete = original_complete

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["mode"], "reply")
        self.assertIsNone(payload["tool_name"])
        self.assertIn("Todavía no tengo", payload["reply"])
        self.assertNotIn("Buscando vuelos", payload["reply"])


if __name__ == "__main__":
    unittest.main()
