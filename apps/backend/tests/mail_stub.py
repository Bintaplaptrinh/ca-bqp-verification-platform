"""Capture outgoing mail instead of talking to Gmail.

The mailer has exactly one transport now (Gmail SMTP with an app password), so
there is no offline file transport for tests to read back. This stands in for
the socket: it exercises the real `send_email` path — recipient validation,
message building, the From derived from GMAIL_USER — and records the
`EmailMessage` that would have gone out, so a test can still prove the password
reached the officer through the mail rather than through the API response.
"""

from __future__ import annotations

from email.message import EmailMessage

SENT: list[EmailMessage] = []


class StubSMTP:
    def __init__(self, host: str, port: int, timeout: float | None = None):
        self.host = host
        self.port = port
        self.timeout = timeout

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def starttls(self, *_args, **_kwargs):
        return None

    def login(self, username: str, password: str):
        # A blank credential is the mistake worth catching here: Gmail refuses
        # it, and silently "succeeding" would hide a misconfigured deployment.
        assert username and password, "Gmail SMTP requires GMAIL_USER and GMAIL_APP_PASSWORD"
        return None

    def send_message(self, message: EmailMessage):
        SENT.append(message)


def install(monkeypatch) -> list[EmailMessage]:
    from cabqp.modules.notifications import email as mailer

    SENT.clear()
    monkeypatch.setattr(mailer.smtplib, "SMTP", StubSMTP)
    return SENT
