"""Settings, read from environment variables (and .env for local development).

Secrets only ever live in environment variables: nothing here is written to
code, logs or the browser. The .env file is never committed (see .gitignore).
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / ".env"
PLACEHOLDER_SECRETS = {"", "change-me", "changeme", "secret"}


def load_env_file(path: Path | None = None) -> None:
    """Load KEY=VALUE pairs from .env without overriding real environment values."""
    path = path or ENV_FILE
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class Settings:
    app_secret: str
    database_path: str
    media_path: str = "data/medicine-images"
    environment: str = "development"
    base_url: str = "http://localhost:8000"
    email_api_key: str = ""
    email_from: str = "no-reply@code4care.my"
    email_api_url: str = "https://api.resend.com/emails"
    google_client_id: str = ""
    google_client_secret: str = ""
    google_auth_url: str = "https://accounts.google.com/o/oauth2/v2/auth"
    google_token_url: str = "https://oauth2.googleapis.com/token"
    google_userinfo_url: str = "https://openidconnect.googleapis.com/v1/userinfo"
    payment_api_key: str = ""
    payment_webhook_secret: str = ""
    support_email: str = "sokongan@code4care.my"
    support_whatsapp: str = "+60123456789"
    session_ttl_seconds: int = 8 * 60 * 60
    login_code_ttl_seconds: int = 15 * 60
    two_factor_ttl_seconds: int = 5 * 60
    pending_cookie_ttl_seconds: int = 10 * 60
    lockout_threshold: int = 5
    lockout_window_seconds: int = 15 * 60
    outbound_timeout_seconds: float = 5.0
    outbound_retries: int = 2

    @classmethod
    def from_env(cls) -> "Settings":
        load_env_file()
        secret = os.environ.get("APP_SECRET", "")
        environment = os.environ.get("ENVIRONMENT", "development")
        if environment == "production" and secret.strip().lower() in PLACEHOLDER_SECRETS:
            raise RuntimeError(
                "APP_SECRET must be a long random value before running in production"
            )
        if not secret:
            raise RuntimeError(
                "APP_SECRET is required. Copy .env.example to .env and set APP_SECRET."
            )
        return cls(
            app_secret=secret,
            database_path=os.environ.get("DATABASE_PATH", "data/code4care.db"),
            media_path=os.environ.get("MEDIA_PATH", "data/medicine-images"),
            environment=environment,
            base_url=os.environ.get("BASE_URL", "http://localhost:8000"),
            email_api_key=os.environ.get("EMAIL_API_KEY", ""),
            email_from=os.environ.get("EMAIL_FROM", "no-reply@code4care.my"),
            email_api_url=os.environ.get("EMAIL_API_URL", "https://api.resend.com/emails"),
            google_client_id=os.environ.get("GOOGLE_CLIENT_ID", ""),
            google_client_secret=os.environ.get("GOOGLE_CLIENT_SECRET", ""),
            payment_api_key=os.environ.get("PAYMENT_API_KEY", ""),
            payment_webhook_secret=os.environ.get("PAYMENT_WEBHOOK_SECRET", ""),
            support_email=os.environ.get("SUPPORT_EMAIL", "sokongan@code4care.my"),
            support_whatsapp=os.environ.get("SUPPORT_WHATSAPP", "+60123456789"),
            session_ttl_seconds=_int("SESSION_TTL_SECONDS", 8 * 60 * 60),
        )

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def is_testing(self) -> bool:
        return self.environment == "testing"

    @property
    def dev_sign_in(self) -> bool:
        """One-click sign-in for local development only; never in production."""
        return self.environment == "development"

    @property
    def database(self) -> Path:
        path = Path(self.database_path)
        return path if path.is_absolute() else (ROOT / path)

    @property
    def media_dir(self) -> Path:
        path = Path(self.media_path)
        return path if path.is_absolute() else (ROOT / path)

    def __repr__(self) -> str:  # never print secrets
        return f"Settings(environment={self.environment!r}, database_path={self.database_path!r})"
