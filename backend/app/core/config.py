from pydantic import model_validator
from pydantic_settings import BaseSettings
from typing import List

class Settings(BaseSettings):
    APP_NAME: str = "AI Assistant"
    ENV: str = "local"
    DEBUG: bool = False
    API_V1_PREFIX: str = "/api/v1"

    DATABASE_URL: str = "postgresql+asyncpg://user:pass@localhost:5432/ai_assistant"
    REDIS_URL: str = "redis://localhost:6379/0"

    SECRET_KEY: str = "change-me-in-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    OPENAI_API_KEY: str = ""
    AI_MODEL: str = "gpt-4o"
    AI_CONFIDENCE_THRESHOLD: float = 0.75
    VOICE_STT_MODEL: str = "whisper-1"
    VOICE_TTS_MODEL: str = "tts-1"
    VOICE_TTS_VOICE: str = "nova"
    VOICE_TTS_RESPONSE_FORMAT: str = "mp3"
    VOICE_MAX_AUDIO_BYTES: int = 10 * 1024 * 1024

    GOOGLE_OAUTH_CLIENT_ID: str = ""
    GOOGLE_OAUTH_CLIENT_SECRET: str = ""
    GOOGLE_OAUTH_REDIRECT_URI: str = ""

    PUBLIC_APP_URL: str = "http://localhost:8000"
    EMAIL_FROM: str = "ARI <no-reply@ari.local>"
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_USE_TLS: bool = True
    PASSWORD_RESET_TOKEN_EXPIRE_MINUTES: int = 30

    DUFFEL_ACCESS_TOKEN: str = ""
    DUFFEL_API_BASE_URL: str = "https://api.duffel.com"
    DUFFEL_API_VERSION: str = "v2"
    DUFFEL_TEST_MODE: bool = True
    DUFFEL_SUPPLIER_TIMEOUT_MS: int = 10000

    MEMORY_ROOT: str = "data/memory"
    SYNC_STORAGE_ROOT: str = "data/sync"
    SYNC_STORAGE_BACKEND: str = "local"
    S3_ENDPOINT_URL: str = ""
    S3_BUCKET: str = ""
    S3_REGION: str = "us-east-1"
    S3_ACCESS_KEY_ID: str = ""
    S3_SECRET_ACCESS_KEY: str = ""

    RATE_LIMIT_ENABLED: bool = False
    RATE_LIMIT_REQUESTS: int = 120
    RATE_LIMIT_WINDOW_SECONDS: int = 60
    RATE_LIMIT_REDIS_PREFIX: str = "rate-limit"

    ALLOWED_ORIGINS: List[str] = ["http://localhost:3000", "tauri://localhost"]

    @model_validator(mode="after")
    def validate_production_settings(self):
        if self.ENV in {"staging", "production"}:
            if self.SECRET_KEY == "change-me-in-production":
                raise ValueError("SECRET_KEY must be set for staging/production")
            if not self.ALLOWED_ORIGINS:
                raise ValueError("ALLOWED_ORIGINS must be explicit for staging/production")
            if self.SYNC_STORAGE_BACKEND == "s3" and not self.S3_BUCKET:
                raise ValueError("S3_BUCKET is required when SYNC_STORAGE_BACKEND=s3")
            if bool(self.GOOGLE_OAUTH_CLIENT_ID) != bool(self.GOOGLE_OAUTH_CLIENT_SECRET):
                raise ValueError("GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET must be set together")
            if bool(self.SMTP_USERNAME) != bool(self.SMTP_PASSWORD):
                raise ValueError("SMTP_USERNAME and SMTP_PASSWORD must be set together")
        if self.SYNC_STORAGE_BACKEND not in {"local", "s3"}:
            raise ValueError("SYNC_STORAGE_BACKEND must be local or s3")
        if self.RATE_LIMIT_REQUESTS < 1:
            raise ValueError("RATE_LIMIT_REQUESTS must be at least 1")
        if self.RATE_LIMIT_WINDOW_SECONDS < 1:
            raise ValueError("RATE_LIMIT_WINDOW_SECONDS must be at least 1")
        return self

    class Config:
        env_file = (".env", ".env.local")

settings = Settings()
