import unittest

from app.api.v1.endpoints import auth
from app.services.email import _auth_email_template


class AuthRecoveryEmailTest(unittest.TestCase):
    def test_reset_token_hash_is_stable_and_not_raw_token(self):
        token = "recovery-token"

        token_hash = auth._hash_reset_token(token)

        self.assertEqual(token_hash, auth._hash_reset_token(token))
        self.assertNotEqual(token_hash, token)
        self.assertEqual(len(token_hash), 64)

    def test_auth_email_template_uses_ari_branding(self):
        html = _auth_email_template(
            eyebrow="Recuperacion segura",
            title="Restablece tu acceso",
            body="Este enlace vence pronto.",
            cta_label="Crear nueva contrasena",
            cta_url="https://ari.example/reset",
            footer="Si no fuiste tu, ignora este mensaje.",
        )

        self.assertIn("Solara", html)
        self.assertIn("<span style=\"color:#C9A96E;\">A</span>ri", html)
        self.assertIn("Restablece tu acceso", html)
        self.assertIn("https://ari.example/reset", html)


if __name__ == "__main__":
    unittest.main()
