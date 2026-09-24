"""Outgoing mail over Gmail SMTP.

An issued password reaches the officer by email, so delivery is part of the
account-creation contract rather than a side effect. There is exactly one
transport: Gmail's submission endpoint (``smtp.gmail.com:587``, STARTTLS),
authenticated with a Google **app password** on ``GMAIL_USER`` /
``GMAIL_APP_PASSWORD``. The self-hosted SMTP settings and the offline ``.eml``
file writer that used to stand in for them were removed — a configurable host
meant a deployment could quietly point issued passwords at an unauthenticated
relay, and the file transport left them sitting in a local directory.

Gmail rejects a ``From`` that is not the authenticated mailbox or one of its
verified aliases, so the envelope sender is always derived from ``GMAIL_USER``;
``MAIL_FROM_NAME`` only sets the display name in front of it.

Messages are MIME multipart: ``multipart/related`` carrying a
``multipart/alternative`` (plain text + HTML) plus the app's own logo as an
inline part the HTML references by ``cid:``. The plain-text alternative is
written to be read on its own, not as a stub — some clients still show it, and
it is what a screen reader and a text-mode client get. The markup lives in
``templates.py``.

The caller is always told whether delivery succeeded; nothing here silently
swallows a failure, because "the password was emailed" is a claim an
administrator will act on.
"""

from __future__ import annotations

import logging
import re
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid
from functools import lru_cache
from pathlib import Path

from cabqp.modules.notifications import templates
from cabqp.shared.settings import get_settings

logger = logging.getLogger(__name__)

TRANSPORT = "gmail"

# Deliberately permissive: this rejects obvious mistakes (missing @, spaces,
# no dot in the domain) without trying to out-guess RFC 5321 on what a real
# mailbox looks like.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def is_valid_email(value: str | None) -> bool:
    return bool(value and _EMAIL_RE.match(value.strip()))


@dataclass
class DeliveryResult:
    """What actually happened, for the caller to report honestly."""

    ok: bool
    transport: str = TRANSPORT
    detail: str | None = None

    def as_dict(self) -> dict:
        payload = {"ok": self.ok, "transport": self.transport}
        if self.detail:
            payload["detail"] = self.detail
        return payload


#: The app's favicon, shipped inside the package (see pyproject's package-data)
#: rather than read out of ``apps/web`` — the backend container has no copy of
#: the web tree, and a message whose logo depends on a sibling directory would
#: render without it in production.
LOGO_PATH = Path(__file__).with_name("assets") / "logo.png"


@lru_cache(maxsize=1)
def _logo_bytes() -> bytes | None:
    """Read the inline logo once. A missing file degrades, never raises."""
    try:
        return LOGO_PATH.read_bytes()
    except OSError:
        logger.warning("email_logo_missing", extra={"event": {"path": str(LOGO_PATH)}})
        return None


def _build_message(to: str, subject: str, text_body: str, html_body: str | None) -> EmailMessage:
    s = get_settings()
    message = EmailMessage()
    # Gmail rewrites a From it does not own, so the address comes from the
    # authenticated account and only the display name is configurable.
    message["From"] = formataddr((s.mail_from_name, s.gmail_user or ""))
    message["To"] = to
    message["Subject"] = subject
    message["Date"] = formatdate(localtime=True)
    message["Message-ID"] = make_msgid(domain="gmail.com")
    # Auto-generated mail: these keep the message out of vacation responders and
    # out of another system's reply loop.
    message["Auto-Submitted"] = "auto-generated"
    message["X-Auto-Response-Suppress"] = "All"

    message.set_content(text_body)
    if not html_body:
        return message

    # add_alternative turns the message into multipart/alternative; the logo is
    # then added to the HTML part's own related group, so a client that shows
    # the text alternative never sees a stray attachment.
    message.add_alternative(html_body, subtype="html")
    logo = _logo_bytes()
    if logo is not None:
        html_part = message.get_payload()[-1]
        html_part.add_related(
            logo,
            maintype="image",
            subtype="png",
            cid=f"<{templates.LOGO_CID}>",
            filename="logo.png",
            disposition="inline",
        )
    return message


def send_email(to: str, subject: str, text_body: str, html_body: str | None = None) -> DeliveryResult:
    """Deliver one message through Gmail SMTP."""
    s = get_settings()
    if not is_valid_email(to):
        return DeliveryResult(ok=False, detail="INVALID_RECIPIENT")
    if not s.mail_configured:
        return DeliveryResult(ok=False, detail="MAIL_NOT_CONFIGURED")
    message = _build_message(to.strip(), subject, text_body, html_body)
    try:
        with smtplib.SMTP(s.gmail_smtp_host, s.gmail_smtp_port, timeout=s.smtp_timeout_seconds) as server:
            server.starttls()
            server.login(s.gmail_user or "", s.gmail_app_password or "")
            server.send_message(message)
        return DeliveryResult(ok=True)
    except Exception as exc:
        # The message body carries a password, so only the error type is logged.
        logger.warning(
            "email_delivery_failed",
            extra={"event": {"transport": TRANSPORT, "error_type": type(exc).__name__}},
        )
        return DeliveryResult(ok=False, detail=type(exc).__name__)


# --- Account messages --------------------------------------------------------

_NEW_ACCOUNT_SUBJECT = "[CA/BQP] Tài khoản truy cập hệ thống tra cứu"
_RESET_SUBJECT = "[CA/BQP] Mật khẩu truy cập đã được cấp lại"

_NEW_ACCOUNT_INTRO = "Quản trị viên đã cấp cho bạn một tài khoản truy cập hệ thống. Thông tin đăng nhập:"
_RESET_INTRO = (
    "Quản trị viên đã cấp lại mật khẩu cho tài khoản của bạn. "
    "Mọi phiên đăng nhập trước đó đã bị thu hồi. Thông tin đăng nhập mới:"
)


def _send_credentials(
    *, to: str, display_name: str, username: str, password: str, subject: str, intro: str, heading: str
) -> DeliveryResult:
    return send_email(
        to,
        subject,
        templates.credentials_text(
            display_name=display_name, username=username, password=password, intro=intro
        ),
        templates.credentials_html(
            display_name=display_name,
            username=username,
            password=password,
            intro=intro,
            heading=heading,
        ),
    )


def send_new_account_email(*, to: str, display_name: str, username: str, password: str) -> DeliveryResult:
    return _send_credentials(
        to=to,
        display_name=display_name,
        username=username,
        password=password,
        subject=_NEW_ACCOUNT_SUBJECT,
        intro=_NEW_ACCOUNT_INTRO,
        heading="Tài khoản truy cập hệ thống",
    )


def send_password_reset_email(*, to: str, display_name: str, username: str, password: str) -> DeliveryResult:
    return _send_credentials(
        to=to,
        display_name=display_name,
        username=username,
        password=password,
        subject=_RESET_SUBJECT,
        intro=_RESET_INTRO,
        heading="Mật khẩu đã được cấp lại",
    )


def send_login_otp_email(*, to: str, display_name: str, code: str, ttl_seconds: int) -> DeliveryResult:
    """One-time sign-in code.

    The subject deliberately does not carry the code: subject lines show on lock
    screens and in notification previews, which is exactly the shoulder-surfing
    path a second factor is supposed to close.
    """
    return send_email(
        to,
        "[CA/BQP] Mã đăng nhập một lần",
        templates.otp_text(display_name=display_name, code=code, ttl_seconds=ttl_seconds),
        templates.otp_html(display_name=display_name, code=code, ttl_seconds=ttl_seconds),
    )
