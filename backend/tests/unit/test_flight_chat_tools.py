import unittest
from datetime import date

from fastapi import HTTPException, status

from app.api.v1.endpoints import messages
from app.api.v1.endpoints.messages import (
    _format_flight_search_error,
    _format_flight_search_results,
    _maybe_run_chat_tool,
    _normalize_orchestration,
    _should_try_tool_orchestration,
)
from app.services.duffel import FlightOffer, FlightSearchRequest, FlightSearchResponse, FlightSegment


class FlightChatToolsTest(unittest.TestCase):
    def test_should_try_tool_orchestration_for_follow_up_results(self):
        self.assertTrue(
            _should_try_tool_orchestration(
                "dame los resultados",
                "User: desde Valencia a Berlin para mañana, dime horarios",
            )
        )

    def test_format_flight_search_results_includes_real_offer_details(self):
        request = FlightSearchRequest(origin="VLC", destination="BER", departure_date=date(2026, 5, 27))
        response = FlightSearchResponse(
            live_mode=False,
            offer_request_id="orq_123",
            raw_result_count=2,
            results=[
                FlightOffer(
                    id="off_123",
                    total_amount="123.45",
                    total_currency="EUR",
                    owner="Duffel Airways",
                    live_mode=False,
                    expires_at=None,
                    booking_available=True,
                    slices=[
                        [
                            FlightSegment(
                                origin="VLC",
                                destination="BER",
                                departing_at="2026-05-27T08:30:00",
                                arriving_at="2026-05-27T11:15:00",
                                marketing_carrier="Example Air",
                                flight_number="42",
                            )
                        ]
                    ],
                )
            ],
        )

        formatted = _format_flight_search_results(request, response)

        self.assertIn("Encontré 1 opción(es)", formatted)
        self.assertIn("123.45 EUR", formatted)
        self.assertIn("Example Air 42", formatted)
        self.assertIn("directo", formatted)
        self.assertIn("2 ofertas en total", formatted)

    def test_format_flight_search_error_explains_missing_provider(self):
        request = FlightSearchRequest(origin="VLC", destination="BER", departure_date=date(2026, 5, 27))
        formatted = _format_flight_search_error(
            request,
            HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="DUFFEL_ACCESS_TOKEN is not configured."),
        )

        self.assertIn("proveedor de vuelos no está configurado", formatted)
        self.assertIn("VLC -> BER", formatted)

    def test_normalize_orchestration_maps_city_names_to_iata(self):
        response = _normalize_orchestration(
            {
                "mode": "tool_ready",
                "reply": "Busco vuelos.",
                "tool_name": "search_flights",
                "params": {
                    "origin": "Valencia",
                    "destination": "Berlín",
                    "departure_date": "2026-05-27",
                },
                "missing": [],
                "requires_confirmation": False,
                "confidence": 0.92,
                "language": "es",
            },
            [],
        )

        self.assertEqual(response.mode, "tool_ready")
        self.assertEqual(response.params["origin"], "VLC")
        self.assertEqual(response.params["destination"], "BER")
        self.assertEqual(response.missing, [])


class FlightChatToolExecutionTest(unittest.IsolatedAsyncioTestCase):
    async def test_maybe_run_chat_tool_executes_ready_flight_search(self):
        original_complete = messages.complete
        original_search_flights = messages.search_flights

        async def fake_complete(prompt, system_prompt=None):
            return """
            {
              "mode": "tool_ready",
              "reply": "Buscando vuelos reales.",
              "tool_name": "search_flights",
              "params": {
                "origin": "VLC",
                "destination": "BER",
                "departure_date": "2026-05-27",
                "passengers": 1
              },
              "missing": [],
              "requires_confirmation": false,
              "confidence": 0.95,
              "language": "es"
            }
            """

        async def fake_search_flights(request):
            self.assertEqual(request.origin, "VLC")
            self.assertEqual(request.destination, "BER")
            return FlightSearchResponse(
                live_mode=False,
                offer_request_id="orq_123",
                raw_result_count=1,
                results=[
                    FlightOffer(
                        id="off_123",
                        total_amount="99.99",
                        total_currency="EUR",
                        owner="Duffel Airways",
                        live_mode=False,
                        expires_at=None,
                        booking_available=True,
                        slices=[
                            [
                                FlightSegment(
                                    origin="VLC",
                                    destination="BER",
                                    departing_at="2026-05-27T06:00:00",
                                    arriving_at="2026-05-27T09:10:00",
                                    marketing_carrier="Example Air",
                                    flight_number="7",
                                )
                            ]
                        ],
                    )
                ],
            )

        messages.complete = fake_complete
        messages.search_flights = fake_search_flights
        try:
            reply = await _maybe_run_chat_tool(
                "dame los resultados",
                "User: desde Valencia a Berlin para mañana, dime horarios",
                "",
                [],
            )
        finally:
            messages.complete = original_complete
            messages.search_flights = original_search_flights

        self.assertIsNotNone(reply)
        self.assertIn("99.99 EUR", reply)
        self.assertIn("Example Air 7", reply)


if __name__ == "__main__":
    unittest.main()
