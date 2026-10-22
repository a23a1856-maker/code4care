"""Email sending: a real provider in production, the console in development.

Email is only used for sign-in links and one-time two-factor codes.
"""
from __future__ import annotations

import sys

from app.config import Settings
from app.outbound import OutboundError, request_with_retry


class ConsoleEmailer:
    """Development only: print the message so a developer can follow the link."""

    def __init__(self, stream=None):
        self.stream = stream or sys.stdout

    def send(self, to: str, subject: str, text: str) -> None:
        print(f"\n--- email (development) to={to} subject={subject} ---\n{text}\n", file=self.stream)


class HttpEmailer:
    def __init__(self, settings: Settings):
        self.settings = settings

    def send(self, to: str, subject: str, text: str) -> None:
        if not self.settings.email_api_key:
            raise OutboundError("EMAIL_API_KEY is not set")
        request_with_retry(
            "POST",
            self.settings.email_api_url,
            headers={
                "Authorization": f"Bearer {self.settings.email_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "from": self.settings.email_from,
                "to": [to],
                "subject": subject,
                "text": text,
            },
            timeout=self.settings.outbound_timeout_seconds,
            retries=self.settings.outbound_retries,
        )


def build_emailer(settings: Settings):
    if settings.email_api_key:
        return HttpEmailer(settings)
    return ConsoleEmailer()
