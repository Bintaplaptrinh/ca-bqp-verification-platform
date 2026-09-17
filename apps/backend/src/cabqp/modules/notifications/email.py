"""Outgoing mail.

An issued password reaches the officer by email, so delivery is part of the
account-creation contract rather than a side effect. Two transports sit behind
one call:

- ``smtp`` — a real server, once ``SMTP_HOST`` is configured.
- ``file`` — writes the message to ``MAIL_OUTBOX_DIR`` as ``.eml`` when no host
  is configured, so the flow is demonstrable on a machine with no mail server.
  ``Settings.production_guards`` refuses to start production in this mode,
  because it would leave issued passwords sitting in a local directory.

The caller is always told which transport ran and whether it succeeded; nothing
here silently swallows a failure, because "the password was emailed" is a claim
an administrator will act on.
"""

from __future__ import annotations

import logging
import re
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formatdate, make_msgid

from cabqp.shared.models import utcnow
from cabqp.shared.settings import get_settings

logger = logging.getLogger(__name__)

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
    transport: str
    detail: str | None = None
    path: str | None = None

    def as_dict(self) -> dict:
        payload = {"ok": self.ok, "transport": self.transport}
        if self.detail:
            payload["detail"] = self.detail
        if self.path:
            payload["path"] = self.path
        return payload


def _build_message(to: str, subject: str, body: str) -> EmailMessage:
    s = get_settings()
    message = EmailMessage()
    message["From"] = s.mail_from
    message["To"] = to
    message["Subject"] = subject
    message["Date"] = formatdate(localtime=True)
    message["Message-ID"] = make_msgid(domain="cabqp.local")
    message.set_content(body)
    return message


def _send_via_smtp(message: EmailMessage) -> DeliveryResult:
    s = get_settings()
    try:
        with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=s.smtp_timeout_seconds) as server:
            if s.smtp_use_tls:
                server.starttls()
            if s.smtp_username:
                server.login(s.smtp_username, s.smtp_password or "")
            server.send_message(message)
        return DeliveryResult(ok=True, transport="smtp")
    except Exception as exc:
        # The message body carries a password, so only the error type is logged.
        logger.warning(
            "email_delivery_failed",
            extra={"event": {"transport": "smtp", "error_type": type(exc).__name__}},
        )
        return DeliveryResult(ok=False, transport="smtp", detail=type(exc).__name__)


def _send_via_file(message: EmailMessage) -> DeliveryResult:
    s = get_settings()
    try:
        outbox = s.mail_outbox_path
        outbox.mkdir(parents=True, exist_ok=True)
        stamp = utcnow().strftime("%Y%m%dT%H%M%S%f")
        safe_to = re.sub(r"[^A-Za-z0-9._@-]+", "_", message["To"])
        path = outbox / f"{stamp}_{safe_to}.eml"
        path.write_text(message.as_string(), encoding="utf-8")
        logger.info(
            "email_written_to_outbox",
            extra={"event": {"transport": "file", "path": str(path)}},
        )
        return DeliveryResult(ok=True, transport="file", path=str(path))
    except Exception as exc:
        logger.warning(
            "email_delivery_failed",
            extra={"event": {"transport": "file", "error_type": type(exc).__name__}},
        )
        return DeliveryResult(ok=False, transport="file", detail=type(exc).__name__)


def send_email(to: str, subject: str, body: str) -> DeliveryResult:
    """Deliver one message through the configured transport."""
    if not is_valid_email(to):
        return DeliveryResult(ok=False, transport=get_settings().mail_transport, detail="INVALID_RECIPIENT")
    message = _build_message(to.strip(), subject, body)
    if get_settings().mail_transport == "smtp":
        return _send_via_smtp(message)
    return _send_via_file(message)


# --- Account messages --------------------------------------------------------


def _credentials_body(*, display_name: str, username: str, password: str, intro: str) -> str:
    return (
        f"Kính gửi {display_name},\n\n"
        f"{intro}\n\n"
        f"    Tên đăng nhập : {username}\n"
        f"    Mật khẩu      : {password}\n\n"
        "Vui lòng đăng nhập và đổi mật khẩu ngay trong lần sử dụng đầu tiên.\n"
        "Không chuyển tiếp thư này và không chia sẻ mật khẩu cho người khác.\n\n"
        "Nếu bạn không yêu cầu tài khoản này, hãy báo ngay cho quản trị viên hệ thống.\n\n"
        "---\n"
        "Hệ thống tra cứu, xác minh đối tượng và hỗ trợ nghiệp vụ an sinh CA/BQP\n"
        "Thư tự động, vui lòng không trả lời.\n"
    )


def send_new_account_email(*, to: str, display_name: str, username: str, password: str) -> DeliveryResult:
    return send_email(
        to,
        "[CA/BQP] Tài khoản truy cập hệ thống tra cứu",
        _credentials_body(
            display_name=display_name,
            username=username,
            password=password,
            intro="Quản trị viên đã cấp cho bạn một tài khoản truy cập hệ thống. Thông tin đăng nhập:",
        ),
    )


def send_password_reset_email(*, to: str, display_name: str, username: str, password: str) -> DeliveryResult:
    return send_email(
        to,
        "[CA/BQP] Mật khẩu truy cập đã được cấp lại",
        _credentials_body(
            display_name=display_name,
            username=username,
            password=password,
            intro=(
                "Quản trị viên đã cấp lại mật khẩu cho tài khoản của bạn. "
                "Mọi phiên đăng nhập trước đó đã bị thu hồi. Thông tin đăng nhập mới:"
            ),
        ),
    )
