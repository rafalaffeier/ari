import unittest
from datetime import date

from fastapi import HTTPException, status

from app.api.v1.endpoints import messages
from app.api.v1.endpoints.messages import (
    _format_gmail_error,
    _format_gmail_search_results,
    _format_gmail_thread_results,
    _format_google_drive_search_error,
    _format_google_drive_search_results,
    _format_flight_search_error,
    _format_flight_search_results,
    _maybe_run_chat_tool,
    _normalize_orchestration,
    _should_try_tool_orchestration,
)
from app.services.duffel import FlightOffer, FlightSearchRequest, FlightSearchResponse, FlightSegment
from app.services.google_drive import GoogleDriveFileMetadata, GoogleDriveSearchResponse
from app.services.google_gmail import GmailMessageSummary, GmailSearchResponse, GmailThreadMessage, GmailThreadResponse


class FlightChatToolsTest(unittest.TestCase):
    def test_should_try_tool_orchestration_for_follow_up_results(self):
        self.assertTrue(
            _should_try_tool_orchestration(
                "dame los resultados",
                "User: desde Valencia a Berlin para mañana, dime horarios",
            )
        )

    def test_should_try_tool_orchestration_for_drive_search(self):
        self.assertTrue(_should_try_tool_orchestration("busca contrato marco en Drive", ""))

    def test_should_try_tool_orchestration_for_gmail_search(self):
        self.assertTrue(_should_try_tool_orchestration("busca correos de Laura en Gmail", ""))

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

    def test_format_google_drive_results_uses_metadata_only(self):
        formatted = _format_google_drive_search_results(
            "contrato",
            GoogleDriveSearchResponse(
                files=[
                    GoogleDriveFileMetadata(
                        id="file_123",
                        name="Contrato marco",
                        mimeType="application/vnd.google-apps.document",
                        webViewLink="https://drive.google.com/file/d/file_123/view",
                        modifiedTime="2026-05-28T10:15:00.000Z",
                        owners=["Rafa"],
                    )
                ],
            ),
        )

        self.assertIn("Contrato marco", formatted)
        self.assertIn("Google Docs", formatted)
        self.assertIn("https://drive.google.com/file/d/file_123/view", formatted)
        self.assertIn("Solo revisé metadatos", formatted)

    def test_format_google_drive_missing_scope_asks_to_reconnect(self):
        formatted = _format_google_drive_search_error(
            HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": "needs_scope", "scope": "https://www.googleapis.com/auth/drive.metadata.readonly"},
            )
        )

        self.assertIn("Reconectar Google", formatted)
        self.assertIn("solo buscaré metadatos", formatted)

    def test_format_gmail_search_results_includes_thread_ids(self):
        formatted = _format_gmail_search_results(
            "from:laura",
            GmailSearchResponse(
                messages=[
                    GmailMessageSummary(
                        id="msg_1",
                        threadId="thr_1",
                        subject="Viaje",
                        from_email="Laura <laura@example.com>",
                        date="2026-05-28T10:15:00+00:00",
                        snippet="Te paso opciones.",
                    )
                ]
            ),
        )

        self.assertIn("Viaje", formatted)
        self.assertIn("thr_1", formatted)
        self.assertIn("Para leer uno", formatted)

    def test_format_gmail_thread_results_does_not_offer_send(self):
        formatted = _format_gmail_thread_results(
            GmailThreadResponse(
                id="thr_1",
                messages=[
                    GmailThreadMessage(
                        id="msg_1",
                        threadId="thr_1",
                        subject="Viaje",
                        from_email="Laura <laura@example.com>",
                        date="2026-05-28T10:15:00+00:00",
                        text="Hola, te paso opciones para el viaje.",
                    )
                ],
            )
        )

        self.assertIn("Hola, te paso opciones", formatted)
        self.assertIn("todavía no creo borradores ni envío emails", formatted)

    def test_format_gmail_missing_scope_asks_to_reconnect(self):
        formatted = _format_gmail_error(
            HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": "needs_scope", "scope": "https://www.googleapis.com/auth/gmail.readonly"},
            )
        )

        self.assertIn("Reconectar Google", formatted)
        self.assertIn("solo puedo buscar y leer", formatted)

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

    async def test_maybe_run_chat_tool_executes_ready_drive_search(self):
        original_complete = messages.complete
        original_valid_token = messages._valid_google_access_token
        original_search_drive = messages.search_google_drive_files_with_token

        async def fake_complete(prompt, system_prompt=None):
            return """
            {
              "mode": "tool_ready",
              "reply": "Buscando en Drive.",
              "tool_name": "search_google_drive_files",
              "params": {
                "query": "contrato",
                "page_size": 5
              },
              "missing": [],
              "requires_confirmation": false,
              "confidence": 0.95,
              "language": "es"
            }
            """

        async def fake_valid_token(db, user_id, required_scope=None):
            self.assertEqual(required_scope, "https://www.googleapis.com/auth/drive.metadata.readonly")
            return "token"

        async def fake_search_drive(access_token, query, page_size=10, page_token=None):
            self.assertEqual(access_token, "token")
            self.assertEqual(query, "contrato")
            self.assertEqual(page_size, 5)
            return GoogleDriveSearchResponse(
                files=[
                    GoogleDriveFileMetadata(
                        id="file_123",
                        name="Contrato marco",
                        mimeType="application/pdf",
                        webViewLink="https://drive.google.com/file/d/file_123/view",
                        modifiedTime="2026-05-28T10:15:00.000Z",
                    )
                ]
            )

        messages.complete = fake_complete
        messages._valid_google_access_token = fake_valid_token
        messages.search_google_drive_files_with_token = fake_search_drive
        try:
            reply = await _maybe_run_chat_tool(
                "busca contrato en Drive",
                "",
                "",
                [],
                db=object(),
                current_user_id=messages.uuid.UUID("22222222-2222-2222-2222-222222222222"),
            )
        finally:
            messages.complete = original_complete
            messages._valid_google_access_token = original_valid_token
            messages.search_google_drive_files_with_token = original_search_drive

        self.assertIsNotNone(reply)
        self.assertIn("Contrato marco", reply)
        self.assertIn("PDF", reply)

    async def test_maybe_run_chat_tool_executes_ready_gmail_search(self):
        original_complete = messages.complete
        original_valid_token = messages._valid_google_access_token
        original_search_gmail = messages.search_gmail_messages_with_token

        async def fake_complete(prompt, system_prompt=None):
            return """
            {
              "mode": "tool_ready",
              "reply": "Buscando en Gmail.",
              "tool_name": "search_gmail_messages",
              "params": {
                "query": "from:laura",
                "max_results": 5
              },
              "missing": [],
              "requires_confirmation": false,
              "confidence": 0.95,
              "language": "es"
            }
            """

        async def fake_valid_token(db, user_id, required_scope=None):
            self.assertEqual(required_scope, "https://www.googleapis.com/auth/gmail.readonly")
            return "token"

        async def fake_search_gmail(access_token, query, max_results=10, page_token=None):
            self.assertEqual(access_token, "token")
            self.assertEqual(query, "from:laura")
            self.assertEqual(max_results, 5)
            return GmailSearchResponse(
                messages=[
                    GmailMessageSummary(
                        id="msg_1",
                        threadId="thr_1",
                        subject="Viaje",
                        from_email="Laura <laura@example.com>",
                        date="2026-05-28T10:15:00+00:00",
                    )
                ]
            )

        messages.complete = fake_complete
        messages._valid_google_access_token = fake_valid_token
        messages.search_gmail_messages_with_token = fake_search_gmail
        try:
            reply = await _maybe_run_chat_tool(
                "busca emails de Laura",
                "",
                "",
                [],
                db=object(),
                current_user_id=messages.uuid.UUID("22222222-2222-2222-2222-222222222222"),
            )
        finally:
            messages.complete = original_complete
            messages._valid_google_access_token = original_valid_token
            messages.search_gmail_messages_with_token = original_search_gmail

        self.assertIsNotNone(reply)
        self.assertIn("Viaje", reply)
        self.assertIn("thr_1", reply)


if __name__ == "__main__":
    unittest.main()
