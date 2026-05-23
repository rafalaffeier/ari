import unittest
import uuid

try:
    from fastapi.testclient import TestClient
except ModuleNotFoundError:
    TestClient = None

if TestClient is not None:
    from fastapi import Path

    from app.api.deps import require_workspace_access
    from app.api.v1.endpoints import travel
    from app.main import app
    from app.services.duffel import FlightSearchResponse


WORKSPACE_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")


if TestClient is not None:
    async def workspace_access_override(workspace_id: uuid.UUID = Path(...)):
        return workspace_id


@unittest.skipIf(TestClient is None, "FastAPI dependencies are not installed")
class TravelApiTest(unittest.TestCase):
    def setUp(self):
        app.dependency_overrides[require_workspace_access] = workspace_access_override
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()

    def test_search_flights_endpoint_calls_duffel_service(self):
        original_search_flights = travel.search_flights

        async def fake_search_flights(body):
            self.assertEqual(body.origin, "BCN")
            self.assertEqual(body.destination, "NRT")
            self.assertEqual(body.passengers, 1)
            return FlightSearchResponse(
                live_mode=False,
                offer_request_id="orq_test",
                results=[],
                raw_result_count=0,
            )

        travel.search_flights = fake_search_flights
        try:
            response = self.client.post(
                f"/api/v1/travel/{WORKSPACE_ID}/flights/search",
                json={
                    "origin": "bcn",
                    "destination": "nrt",
                    "departure_date": "2026-07-10",
                    "return_date": "2026-07-24",
                },
            )
        finally:
            travel.search_flights = original_search_flights

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["provider"], "duffel")
        self.assertEqual(response.json()["offer_request_id"], "orq_test")


if __name__ == "__main__":
    unittest.main()
