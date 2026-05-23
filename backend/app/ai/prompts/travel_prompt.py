def build_travel_prompt(user_input: str) -> str:
    return f"""
Extract travel search parameters from the user's request.

Respond ONLY with a JSON object:
{{
  "intent": "<short description>",
  "tool": "search_flights" | "search_hotels" | "search_trip_package",
  "confidence": <float>,
  "params": {{
    "origin": "<IATA code or city>",
    "destination": "<IATA code or city>",
    "departure_date": "<YYYY-MM-DD>",
    "return_date": "<YYYY-MM-DD or null>",
    "passengers": <int>,
    "budget": <float or null>,
    "preferences": {{}}
  }}
}}

User request: {user_input}
""".strip()
