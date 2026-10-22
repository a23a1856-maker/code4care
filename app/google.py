"""Google sign-in: the OAuth 2.0 authorisation code flow, over HTTPS."""
from __future__ import annotations

from urllib.parse import urlencode

from app.config import Settings
from app.outbound import OutboundError, parse_json, request_with_retry


class GoogleOAuthClient:
    """Exchanges a callback code for a verified profile; never sees a password."""

    def __init__(self, settings: Settings):
        self.settings = settings

    def _redirect_uri(self) -> str:
        return f"{self.settings.base_url.rstrip('/')}/auth/google/callback"

    def authorize_url(self, state: str) -> str:
        params = {
            "client_id": self.settings.google_client_id,
            "redirect_uri": self._redirect_uri(),
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            "prompt": "select_account",
        }
        return f"{self.settings.google_auth_url}?{urlencode(params)}"

    def exchange_code(self, code: str) -> dict:
        settings = self.settings
        if not settings.google_client_id or not settings.google_client_secret:
            raise OutboundError("Google sign-in is not configured")
        token_response = request_with_retry(
            "POST",
            settings.google_token_url,
            data={
                "code": code,
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "redirect_uri": self._redirect_uri(),
                "grant_type": "authorization_code",
            },
            timeout=settings.outbound_timeout_seconds,
            retries=settings.outbound_retries,
        )
        token_payload = parse_json(token_response)
        access_token = token_payload.get("access_token")
        if not access_token:
            raise OutboundError("Google did not return an access token")

        info_response = request_with_retry(
            "GET",
            settings.google_userinfo_url,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=settings.outbound_timeout_seconds,
            retries=settings.outbound_retries,
        )
        info = parse_json(info_response)
        return {
            "email": str(info.get("email", "")),
            "email_verified": bool(info.get("email_verified")),
            "sub": str(info.get("sub", "")),
        }
