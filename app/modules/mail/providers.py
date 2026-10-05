"""Mail providers. All of them take a `Message` and return a provider message id."""
import logging
import smtplib
import time
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import parseaddr

import httpx

from app.config import Settings

log = logging.getLogger("regsite.mail")


class MailError(Exception):
    pass


@dataclass
class Message:
    to: str
    subject: str
    html: str
    text: str
    from_addr: str
    reply_to: str = ""
    idempotency_key: str = ""


class ConsoleProvider:
    """Development provider: writes the email to the log instead of sending it."""

    name = "console"

    def send(self, msg: Message) -> str:
        log.info("EMAIL to=%s subject=%r reply_to=%s\n%s", msg.to, msg.subject, msg.reply_to, msg.text)
        return "console"


class ResendProvider:
    """Sends through Resend's HTTPS API (port 443), see https://resend.com/docs/api-reference/emails/send-email"""

    name = "resend"
    url = "https://api.resend.com/emails"

    def __init__(self, api_key: str):
        self.api_key = api_key

    def send(self, msg: Message) -> str:
        payload = {
            "from": msg.from_addr,
            "to": [msg.to],
            "subject": msg.subject,
            "html": msg.html,
            "text": msg.text,
        }
        if msg.reply_to:
            payload["reply_to"] = msg.reply_to
        headers = {"Authorization": f"Bearer {self.api_key}", "User-Agent": "regsite/1.0"}
        if msg.idempotency_key:
            headers["Idempotency-Key"] = msg.idempotency_key

        last_error = "unknown error"
        for attempt in range(2):
            try:
                resp = httpx.post(self.url, json=payload, headers=headers, timeout=15)
            except httpx.HTTPError as exc:
                last_error = f"network error: {exc}"
            else:
                if resp.status_code < 300:
                    return str(resp.json().get("id", ""))
                try:
                    detail = resp.json().get("message") or resp.text
                except ValueError:
                    detail = resp.text
                last_error = f"Resend returned {resp.status_code}: {detail}"
                if resp.status_code < 500 and resp.status_code != 429:
                    break  # a client error will not fix itself on retry
            if attempt == 0:
                time.sleep(1.5)
        raise MailError(last_error)


class SmtpProvider:
    name = "smtp"

    def __init__(self, settings: Settings):
        self.s = settings

    def send(self, msg: Message) -> str:
        email = EmailMessage()
        email["From"] = msg.from_addr
        email["To"] = msg.to
        email["Subject"] = msg.subject
        if msg.reply_to:
            email["Reply-To"] = msg.reply_to
        email.set_content(msg.text)
        email.add_alternative(msg.html, subtype="html")
        try:
            with smtplib.SMTP(self.s.smtp_host, self.s.smtp_port, timeout=20) as smtp:
                if self.s.smtp_starttls:
                    smtp.starttls()
                if self.s.smtp_user:
                    smtp.login(self.s.smtp_user, self.s.smtp_password)
                smtp.send_message(email, from_addr=parseaddr(msg.from_addr)[1])
        except (OSError, smtplib.SMTPException) as exc:
            raise MailError(f"SMTP error: {exc}") from exc
        return "smtp"


def get_provider(settings: Settings):
    if settings.mail_provider == "resend":
        if not settings.resend_api_key:
            raise MailError("RESEND_API_KEY is not set")
        return ResendProvider(settings.resend_api_key)
    if settings.mail_provider == "smtp":
        if not settings.smtp_host:
            raise MailError("SMTP_HOST is not set")
        return SmtpProvider(settings)
    return ConsoleProvider()
