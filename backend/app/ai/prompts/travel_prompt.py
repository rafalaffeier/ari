def build_travel_prompt(user_input: str) -> str:
    return f"""
Extract travel search parameters from the user's request.
For flight searches, origin and destination must be fixed 3-letter IATA airport or city codes.
If the user says "anywhere", "cualquier parte", or leaves origin/destination flexible, return null for the missing flexible field instead of inventing a route.

Respond ONLY with a JSON object:
{{
  "intent": "<short description>",
  "tool": "search_flights" | "search_hotels" | "search_trip_package",
  "confidence": <float>,
  "params": {{
    "origin": "<IATA code or null>",
    "destination": "<IATA code or null>",
    "departure_date": "<YYYY-MM-DD>",
    "return_date": "<YYYY-MM-DD or null>",
    "passengers": <int>,
    "budget": <float or null>,
    "preferences": {{}}
  }}
}}

User request: {user_input}
""".strip()
