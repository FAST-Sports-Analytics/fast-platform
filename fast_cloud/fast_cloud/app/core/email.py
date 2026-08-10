from __future__ import annotations

import json
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from html import escape
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.core.config import get_settings

settings = get_settings()


@dataclass(frozen=True)
class EmailDelivery:
    delivered: bool
    provider: str
    message_id: str | None = None
    detail: str = ""


class EmailDeliveryError(RuntimeError):
    pass


def _from_header() -> str:
    name = (settings.email_from_name or "FAST Sports Analytics").strip()
    email = (settings.email_from_email or settings.smtp_from_email).strip()
    return f"{name} <{email}>" if name else email


def _send_resend(*, to_email: str, subject: str, text: str, html: str) -> EmailDelivery:
    if not settings.resend_api_key:
        return EmailDelivery(False, "resend", detail="Resend API key is not configured")
    payload: dict[str, object] = {
        "from": _from_header(),
        "to": [to_email],
        "subject": subject,
        "text": text,
        "html": html,
    }
    if settings.email_reply_to:
        payload["reply_to"] = settings.email_reply_to
    request = Request(
        f"{settings.resend_api_base.rstrip('/')}/emails",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {settings.resend_api_key}",
            "Content-Type": "application/json",
            "User-Agent": "FAST-Cloud/1.0",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=settings.email_timeout_seconds) as response:
            body = json.loads(response.read().decode("utf-8") or "{}")
            message_id = str(body.get("id") or "") or None
            return EmailDelivery(True, "resend", message_id=message_id)
    except HTTPError as exc:
        try:
            detail = exc.read().decode("utf-8", errors="replace")
        except Exception:
            detail = str(exc)
        return EmailDelivery(False, "resend", detail=f"HTTP {exc.code}: {detail}")
    except (URLError, TimeoutError, OSError) as exc:
        return EmailDelivery(False, "resend", detail=str(exc))


def _send_smtp(*, to_email: str, subject: str, text: str, html: str) -> EmailDelivery:
    if not settings.smtp_host:
        return EmailDelivery(False, "smtp", detail="SMTP host is not configured")

    message = EmailMessage()
    message["From"] = _from_header()
    message["To"] = to_email
    message["Subject"] = subject
    if settings.email_reply_to:
        message["Reply-To"] = settings.email_reply_to
    message.set_content(text)
    message.add_alternative(html, subtype="html")

    context = ssl.create_default_context()
    try:
        if settings.smtp_ssl:
            client = smtplib.SMTP_SSL(
                settings.smtp_host,
                settings.smtp_port,
                timeout=settings.email_timeout_seconds,
                context=context,
            )
        else:
            client = smtplib.SMTP(
                settings.smtp_host,
                settings.smtp_port,
                timeout=settings.email_timeout_seconds,
            )
        with client:
            if settings.smtp_starttls and not settings.smtp_ssl:
                client.starttls(context=context)
            if settings.smtp_username:
                client.login(settings.smtp_username, settings.smtp_password)
            client.send_message(message)
        return EmailDelivery(True, "smtp")
    except (smtplib.SMTPException, OSError) as exc:
        return EmailDelivery(False, "smtp", detail=str(exc))


def _console(*, to_email: str, subject: str, text: str) -> EmailDelivery:
    print(f"[FAST Cloud email] TO={to_email} SUBJECT={subject}\n{text}\n")
    return EmailDelivery(False, "development_console", detail="Message written to FAST Cloud console")


def send_email(*, to_email: str, subject: str, text: str, html: str) -> EmailDelivery:
    """Deliver a transactional FAST email using the configured provider.

    Production defaults to Resend when ``FAST_CLOUD_RESEND_API_KEY`` is set,
    otherwise SMTP can be selected. Development deliberately falls back to the
    Cloud console so invitation/recovery flows remain testable offline.
    """
    provider = (settings.email_provider or "auto").strip().lower()
    if provider not in {"auto", "resend", "smtp", "console"}:
        raise EmailDeliveryError(f"Unsupported FAST_CLOUD_EMAIL_PROVIDER: {provider}")

    if provider == "console":
        delivery = _console(to_email=to_email, subject=subject, text=text)
    elif provider == "resend":
        delivery = _send_resend(to_email=to_email, subject=subject, text=text, html=html)
    elif provider == "smtp":
        delivery = _send_smtp(to_email=to_email, subject=subject, text=text, html=html)
    else:
        if settings.resend_api_key:
            delivery = _send_resend(to_email=to_email, subject=subject, text=text, html=html)
        elif settings.smtp_host:
            delivery = _send_smtp(to_email=to_email, subject=subject, text=text, html=html)
        else:
            delivery = _console(to_email=to_email, subject=subject, text=text)

    if settings.environment.lower() == "production" and not delivery.delivered:
        raise EmailDeliveryError(
            f"Transactional email delivery failed via {delivery.provider}: {delivery.detail or 'unknown error'}"
        )
    return delivery


def branded_action_email(
    *,
    heading: str,
    intro: str,
    action_label: str,
    action_url: str,
    expiry_text: str,
    footer_text: str,
) -> tuple[str, str]:
    """Return matching plain-text and branded HTML variants."""
    text = (
        f"{heading}\n\n{intro}\n\n{action_label}: {action_url}\n\n"
        f"{expiry_text}\n\n{footer_text}\n\nFAST Sports Analytics\n"
    )
    html = f"""<!doctype html>
<html>
  <body style="margin:0;background:#101416;color:#F4F6F7;font-family:Arial,Helvetica,sans-serif;">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#101416;padding:32px 16px;">
      <tr><td align="center">
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:620px;background:#1E2227;border:1px solid #30373B;border-radius:14px;overflow:hidden;">
          <tr><td style="padding:28px 32px;border-bottom:1px solid #30373B;">
            <div style="font-size:12px;letter-spacing:2px;color:#19D978;font-weight:700;">FAST SPORTS ANALYTICS</div>
          </td></tr>
          <tr><td style="padding:36px 32px;">
            <h1 style="margin:0 0 18px;font-size:28px;line-height:1.2;color:#FFFFFF;">{escape(heading)}</h1>
            <p style="margin:0 0 26px;font-size:16px;line-height:1.6;color:#C8D0D4;">{escape(intro)}</p>
            <p style="margin:0 0 28px;">
              <a href="{escape(action_url, quote=True)}" style="display:inline-block;background:#19D978;color:#08110D;text-decoration:none;font-weight:700;padding:14px 22px;border-radius:8px;">{escape(action_label)}</a>
            </p>
            <p style="margin:0 0 10px;font-size:13px;line-height:1.5;color:#94A0A6;">{escape(expiry_text)}</p>
            <p style="margin:0;font-size:13px;line-height:1.5;color:#94A0A6;">{escape(footer_text)}</p>
          </td></tr>
          <tr><td style="padding:20px 32px;border-top:1px solid #30373B;font-size:12px;color:#6F7B80;">FAST Sports Analytics</td></tr>
        </table>
      </td></tr>
    </table>
  </body>
</html>"""
    return text, html
