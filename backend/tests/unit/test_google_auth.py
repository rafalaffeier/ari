import unittest
import uuid

from app.api.v1.endpoints import auth


class GoogleAuthHelpersTest(unittest.IsolatedAsyncioTestCase):
    async def test_google_exchange_code_round_trip(self):
        payload = auth.TokenResponse(
            access_token="ari-access-token",
            user_id=uuid.uuid4(),
            default_workspace_id=uuid.uuid4(),
            email="user@example.com",
        )

        code = auth._encode_google_exchange_code(payload)
        exchanged = await auth.google_exchange(auth.GoogleExchangeRequest(code=code))

        self.assertEqual(exchanged.access_token, payload.access_token)
        self.assertEqual(exchanged.user_id, payload.user_id)
        self.assertEqual(exchanged.default_workspace_id, payload.default_workspace_id)
        self.assertEqual(exchanged.email, payload.email)

    def test_safe_return_to_blocks_untrusted_absolute_urls(self):
        self.assertEqual(auth._safe_return_to("https://evil.example/callback"), "/")
        self.assertEqual(auth._safe_return_to("/"), "/")
        self.assertEqual(auth._safe_return_to("/welcome"), "/welcome")


if __name__ == "__main__":
    unittest.main()
