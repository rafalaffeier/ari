import unittest

from app.services.duffel import FlightSearchRequest, normalize_offer_request


class DuffelServiceTest(unittest.TestCase):
    def test_flight_search_request_normalizes_iata_codes(self):
        request = FlightSearchRequest(
            origin="bcn",
            destination="nrt",
            departure_date="2026-07-10",
            return_date="2026-07-24",
            passengers=2,
        )

        self.assertEqual(request.origin, "BCN")
        self.assertEqual(request.destination, "NRT")
        self.assertEqual(request.cabin_class, "economy")

    def test_normalizes_and_sorts_offers(self):
        response = normalize_offer_request(
            {
                "id": "orq_test",
                "live_mode": False,
                "offers": [
                    {
                        "id": "off_expensive",
                        "total_amount": "900.00",
                        "total_currency": "EUR",
                        "owner": {"name": "Carrier B"},
                        "live_mode": False,
                        "slices": [],
                    },
                    {
                        "id": "off_cheap",
                        "total_amount": "500.00",
                        "total_currency": "EUR",
                        "owner": {"name": "Carrier A"},
                        "live_mode": False,
                        "slices": [
                            {
                                "segments": [
                                    {
                                        "origin": {"iata_code": "BCN"},
                                        "destination": {"iata_code": "NRT"},
                                        "departing_at": "2026-07-10T08:00:00",
                                        "arriving_at": "2026-07-11T08:00:00",
                                        "marketing_carrier": {"name": "Carrier A"},
                                        "operating_carrier": {"name": "Carrier A"},
                                        "marketing_carrier_flight_number": "123",
                                    }
                                ]
                            }
                        ],
                    },
                ],
            },
            max_results=1,
        )

        self.assertEqual(response.provider, "duffel")
        self.assertEqual(response.offer_request_id, "orq_test")
        self.assertEqual(response.raw_result_count, 2)
        self.assertEqual(len(response.results), 1)
        self.assertEqual(response.results[0].id, "off_cheap")
        self.assertEqual(response.results[0].slices[0][0].origin, "BCN")


if __name__ == "__main__":
    unittest.main()
