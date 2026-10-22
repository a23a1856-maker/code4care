"""Test doubles and helpers shared by the suite."""
from __future__ import annotations

import re
import sqlite3


class FakeEmailer:
    """Records the messages the app would send, so tests can read the link/code."""

    def __init__(self):
        self.messages: list[dict] = []

    def send(self, to: str, subject: str, text: str) -> None:
        self.messages.append({"to": to, "subject": subject, "text": text})


def latest_message(outbox, email: str) -> dict:
    for message in reversed(outbox.messages):
        if message["to"].lower() == email.lower():
            return message
    raise AssertionError(f"no message for {email}; got {[m['to'] for m in outbox.messages]}")


def magic_path(message: dict) -> str:
    match = re.search(r"(/auth/magic\?token=[A-Za-z0-9_\-]+)", message["text"])
    assert match, f"no magic link in message: {message['text']!r}"
    return match.group(1)


def six_digit_code(message: dict) -> str:
    match = re.search(r"\b(\d{6})\b", message["text"])
    assert match, f"no six digit code in message: {message['text']!r}"
    return match.group(1)


def csrf_token(html: str) -> str:
    for pattern in (
        r'name="csrf_token" value="([^"]+)"',
        r'name="csrf-token" content="([^"]+)"',
    ):
        match = re.search(pattern, html)
        if match:
            return match.group(1)
    raise AssertionError("page must carry a CSRF token")


def count(conn: sqlite3.Connection, table: str, tenant_id: int | None = None) -> int:
    if tenant_id is None:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    return conn.execute(
        f"SELECT COUNT(*) FROM {table} WHERE tenant_id = ?", (tenant_id,)
    ).fetchone()[0]
