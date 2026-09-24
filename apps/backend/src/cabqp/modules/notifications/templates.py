"""HTML bodies for the account and sign-in emails.

Mail clients are not browsers. Gmail, Outlook and the Vietnamese webmail clients
these messages land in strip ``<style>`` blocks, ignore flexbox and grid, and
Outlook renders through Word. So the layout here is deliberately old-fashioned:
nested ``<table>`` elements, widths in pixels, every rule as an inline ``style``
attribute, and no external stylesheet or webfont. This is the same shape the
reference message (Riot's login-code mail) uses.

The logo is an inline part referenced as ``cid:``, not a hosted URL: there is no
public place to serve the app's favicon from, and a remote image would be
blocked by default in most clients anyway. ``build_message`` in ``email.py``
attaches it and this module only names the content id.

Everything interpolated into the HTML goes through :func:`esc`. These values are
operator-supplied (a display name, a username) rather than attacker-supplied,
but a name containing ``&`` or ``<`` would still break the markup, and a mail
body is one more render site that must not be assembled by concatenation alone.
"""

from __future__ import annotations

from html import escape

#: Content id of the inline logo part. Kept here so the template and the part
#: that carries the bytes cannot drift apart.
LOGO_CID = "cabqp-logo"

_BRAND = "#b91c1c"
_INK = "#0f172a"
_MUTED = "#64748b"
_LINE = "#e2e8f0"
_CANVAS = "#f1f5f9"

_FONT = (
    "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',Arial,sans-serif"
)

_SYSTEM_NAME = "Hệ thống tra cứu, xác minh đối tượng và hỗ trợ nghiệp vụ an sinh CA/BQP"


def esc(value: str | None) -> str:
    return escape(str(value or ""), quote=True)


def _shell(*, preheader: str, heading: str, body_html: str) -> str:
    """Wrap a block of content in the branded frame.

    ``preheader`` is the grey snippet a client shows next to the subject in the
    inbox list. It is hidden in the body itself; without it the client picks the
    first visible words, which would be the header caption on every message.
    """
    return f"""\
<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light">
<title>{esc(heading)}</title>
</head>
<body style="margin:0;padding:0;background-color:{_CANVAS};">
<div style="display:none;max-height:0;overflow:hidden;opacity:0;color:transparent;font-size:1px;line-height:1px;">{esc(preheader)}</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:{_CANVAS};">
<tr><td align="center" style="padding:24px 12px;">

<table role="presentation" width="600" cellpadding="0" cellspacing="0" border="0" style="width:600px;max-width:100%;background-color:#ffffff;border:1px solid {_LINE};border-radius:10px;overflow:hidden;">

  <tr>
    <td style="background-color:{_BRAND};padding:22px 28px;">
      <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%">
        <tr>
          <td width="52" valign="middle" style="width:52px;padding-right:14px;">
            <img src="cid:{LOGO_CID}" width="52" height="52" alt=""
                 style="display:block;width:52px;height:52px;border:0;outline:none;text-decoration:none;">
          </td>
          <td valign="middle" style="font-family:{_FONT};color:#ffffff;">
            <div style="font-size:15px;font-weight:700;line-height:1.35;">BỘ CÔNG AN - BỘ QUỐC PHÒNG</div>
            <div style="font-size:12px;line-height:1.45;color:#fee2e2;">Hệ thống tra cứu và xác minh đối tượng</div>
          </td>
        </tr>
      </table>
    </td>
  </tr>

  <tr>
    <td style="padding:30px 28px 8px 28px;font-family:{_FONT};">
      <h1 style="margin:0;font-size:20px;line-height:1.35;font-weight:700;color:{_INK};">{esc(heading)}</h1>
    </td>
  </tr>

  <tr>
    <td style="padding:0 28px 28px 28px;font-family:{_FONT};font-size:14px;line-height:1.65;color:{_INK};">
{body_html}
    </td>
  </tr>

  <tr>
    <td style="padding:18px 28px 22px 28px;background-color:#f8fafc;border-top:1px solid {_LINE};font-family:{_FONT};font-size:11.5px;line-height:1.6;color:{_MUTED};">
      {esc(_SYSTEM_NAME)}<br>
      Thư được gửi tự động, vui lòng không trả lời thư này.
    </td>
  </tr>

</table>

</td></tr>
</table>
</body>
</html>
"""


def _paragraph(text: str) -> str:
    return f'      <p style="margin:0 0 14px 0;">{esc(text)}</p>'


def _callout(text: str) -> str:
    """A tinted note for the security warnings at the end of each message."""
    return (
        f'      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
        f'style="margin:6px 0 0 0;background-color:#fef2f2;border-left:3px solid {_BRAND};border-radius:4px;">'
        f'<tr><td style="padding:12px 14px;font-size:12.5px;line-height:1.6;color:#7f1d1d;">{esc(text)}</td></tr>'
        f"</table>"
    )


def _field_rows(rows: list[tuple[str, str]]) -> str:
    """Label/value pairs in the monospace box used for issued credentials."""
    cells = "".join(
        f'<tr>'
        f'<td style="padding:6px 14px 6px 16px;font-size:12.5px;color:{_MUTED};white-space:nowrap;">{esc(label)}</td>'
        f'<td style="padding:6px 16px 6px 0;font-size:14px;font-weight:700;color:{_INK};'
        f"font-family:'SFMono-Regular',Consolas,'Liberation Mono',monospace;word-break:break-all;\">{esc(value)}</td>"
        f"</tr>"
        for label, value in rows
    )
    return (
        '      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
        f'style="margin:4px 0 18px 0;background-color:#f8fafc;border:1px solid {_LINE};border-radius:8px;">'
        f'<tr><td style="padding:6px 0;"><table role="presentation" cellpadding="0" cellspacing="0" border="0">'
        f"{cells}</table></td></tr></table>"
    )


# --- Credentials -------------------------------------------------------------

_CREDENTIAL_WARNING = (
    "Không chuyển tiếp thư này và không chia sẻ mật khẩu cho bất kỳ ai. "
    "Nếu bạn không yêu cầu tài khoản này, hãy báo ngay cho quản trị viên hệ thống."
)


def credentials_text(*, display_name: str, username: str, password: str, intro: str) -> str:
    """The plain-text alternative. Kept readable on its own, not a fallback stub."""
    return (
        f"Kính gửi {display_name},\n\n"
        f"{intro}\n\n"
        f"    Tên đăng nhập : {username}\n"
        f"    Mật khẩu      : {password}\n\n"
        "Vui lòng đăng nhập và đổi mật khẩu ngay trong lần sử dụng đầu tiên.\n"
        f"{_CREDENTIAL_WARNING}\n\n"
        "---\n"
        f"{_SYSTEM_NAME}\n"
        "Thư tự động, vui lòng không trả lời.\n"
    )


def credentials_html(*, display_name: str, username: str, password: str, intro: str, heading: str) -> str:
    body = "\n".join(
        [
            _paragraph(f"Kính gửi {display_name},"),
            _paragraph(intro),
            _field_rows([("Tên đăng nhập", username), ("Mật khẩu", password)]),
            _paragraph("Vui lòng đăng nhập và đổi mật khẩu ngay trong lần sử dụng đầu tiên."),
            _callout(_CREDENTIAL_WARNING),
        ]
    )
    return _shell(preheader=intro, heading=heading, body_html=body)


# --- Sign-in code ------------------------------------------------------------


def _code_block(code: str) -> str:
    """The code itself, letter-spaced and large enough to read on a phone."""
    return (
        '      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
        f'style="margin:4px 0 16px 0;background-color:#f8fafc;border:1px solid {_LINE};border-radius:10px;">'
        f'<tr><td align="center" style="padding:20px 16px;">'
        f'<div style="font-size:34px;line-height:1.15;font-weight:700;letter-spacing:10px;color:{_BRAND};'
        f"font-family:'SFMono-Regular',Consolas,'Liberation Mono',monospace;\">{esc(code)}</div>"
        f"</td></tr></table>"
    )


def otp_text(*, display_name: str, code: str, ttl_seconds: int) -> str:
    return (
        f"Kính gửi {display_name},\n\n"
        "Mã đăng nhập một lần cho tài khoản của bạn:\n\n"
        f"    {code}\n\n"
        f"Mã có hiệu lực trong {ttl_seconds} giây và chỉ dùng được một lần.\n\n"
        "Cán bộ hệ thống không bao giờ hỏi mã này. Nếu bạn không yêu cầu đăng nhập,\n"
        "hãy bỏ qua thư này và đổi mật khẩu tài khoản.\n\n"
        "---\n"
        f"{_SYSTEM_NAME}\n"
        "Thư tự động, vui lòng không trả lời.\n"
    )


def otp_html(*, display_name: str, code: str, ttl_seconds: int) -> str:
    body = "\n".join(
        [
            _paragraph(f"Kính gửi {display_name},"),
            _paragraph("Mã đăng nhập một lần cho tài khoản của bạn:"),
            _code_block(code),
            _paragraph(f"Mã có hiệu lực trong {ttl_seconds} giây và chỉ sử dụng được một lần."),
            _callout(
                "Cán bộ hệ thống không bao giờ hỏi mã này. Nếu bạn không yêu cầu đăng nhập, "
                "hãy bỏ qua thư này và đổi mật khẩu tài khoản."
            ),
        ]
    )
    return _shell(
        preheader=f"Mã đăng nhập có hiệu lực {ttl_seconds} giây",
        heading="Mã đăng nhập một lần",
        body_html=body,
    )
