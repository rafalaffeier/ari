import base64
import hashlib
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import settings


def _key() -> bytes:
    return hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest()


def encrypt_token(token: str) -> str:
    nonce = os.urandom(12)
    encrypted = AESGCM(_key()).encrypt(nonce, token.encode("utf-8"), None)
    return base64.urlsafe_b64encode(nonce + encrypted).decode("ascii")


def decrypt_token(payload: str) -> str:
    raw = base64.urlsafe_b64decode(payload.encode("ascii"))
    nonce, encrypted = raw[:12], raw[12:]
    return AESGCM(_key()).decrypt(nonce, encrypted, None).decode("utf-8")
