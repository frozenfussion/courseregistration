"""Transactional email: student confirmations and decisions, plus the alert to the trainer.

Sending never blocks or breaks a registration. Every attempt is written to `email_log`, and the admin
screen shows any that failed.
"""
import logging
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import SessionLocal
from app.formatting import fmt_date_range, fmt_dt
from app.models import EmailLog, Registration
from app.modules.mail.providers import MailError, Message, get_provider
from app.templating import env

log = logging.getLogger("regsite.mail")

# The shared environment escapes HTML everywhere; plain-text emails must not be escaped.
_text_env = env.overlay(autoescape=False)


@dataclass(frozen=True)
class Copy:
    tag: str
    tone: str
    subject: str
    heading: str
    paragraphs: tuple[str, ...]
    foot: str


COPY: dict[str, Copy] = {
    "received": Copy(
        tag="Received",
        tone="#e3cb98",
        subject="We have received your registration",
        heading="Thank you, {name}.",
        paragraphs=(
            "Your registration request has been received. The trainer reviews each request "
            "personally, and you will get another email as soon as a decision is made. "
            "This message is not a confirmation of your seat.",
        ),
        foot="You are receiving this because you registered on the course page.",
    ),
    "approved": Copy(
        tag="Approved",
        tone="#8fd0a0",
        subject="Your place is confirmed",
        heading="You are in, {name}.",
        paragraphs=(
            "Your registration has been approved and a seat is reserved for you. "
            "If your plans change, please reply to this email so the seat can be released.",
        ),
        foot="Questions? Reply to this email and it will reach the trainer directly.",
    ),
    "kiv": Copy(
        tag="Kept in view (KIV)",
        tone="#d9b46a",
        subject="Your registration is under consideration",
        heading="Your request is on hold, {name}.",
        paragraphs=(
            "Your registration is currently kept in view. This is not a rejection. "
            "If you would like to discuss it, please reply to this email or speak to the trainer directly.",
        ),
        foot="You will receive another email if the status changes.",
    ),
    "rejected": Copy(
        tag="Not approved",
        tone="#eaa59c",
        subject="An update on your registration",
        heading="We could not offer you a place, {name}.",
        paragraphs=(
            "Thank you for your interest. On this occasion your registration was not approved. "
            "If you believe something was entered incorrectly, please reply to this email or speak to "
            "the trainer, who can review your request again.",
        ),
        foot="The trainer can change a decision at any time.",
    ),
}


def _build(kind: str, reg: Registration, note: str = "") -> tuple[str, str, str]:
    """Return (subject, html, text) for a student email."""
    copy = COPY[kind]
    course = reg.course
    ctx = {
        "tag": copy.tag,
        "tone": copy.tone,
        "heading": copy.heading.format(name=reg.name.split()[0] if reg.name.split() else reg.name),
        "paragraphs": list(copy.paragraphs),
        "note": note.strip(),
        "foot": copy.foot,
        "course": course,
        "when": fmt_date_range(course.start_date, course.end_date),
        "venue": course.venue,
        "site_url": get_settings().base_url.rstrip("/"),
        "alert": None,
    }
    return (
        copy.subject,
        env.get_template("emails/email.html").render(**ctx),
        _text_env.get_template("emails/email.txt").render(**ctx),
    )


def _build_alert(reg: Registration) -> tuple[str, str, str]:
    course = reg.course
    base = get_settings().base_url.rstrip("/")
    rows = [
        ("Name", reg.name),
        ("Email", reg.email),
        ("Phone", reg.phone),
        ("Company", reg.company or "—"),
        ("Job title", reg.job_title or "—"),
        ("Notes", reg.notes or "—"),
        ("Submitted", fmt_dt(reg.created_at)),
    ]
    if reg.flagged:
        rows.append(("Flagged", reg.flag_reason))
    ctx = {
        "tag": "New registration",
        "tone": "#e3cb98",
        "heading": f"{reg.name} has registered.",
        "paragraphs": [f"A new registration is waiting for your decision on {course.title}."],
        "note": "",
        "foot": "Reply to this email to write to the student directly.",
        "course": course,
        "when": fmt_date_range(course.start_date, course.end_date),
        "venue": course.venue,
        "site_url": base,
        "alert": {"rows": rows, "url": f"{base}/admin/registrations?course_id={course.id}&status=pending"},
    }
    subject = f"New registration: {reg.name} ({course.title})"
    return (
        subject,
        env.get_template("emails/email.html").render(**ctx),
        _text_env.get_template("emails/email.txt").render(**ctx),
    )


def _deliver(db: Session, *, kind: str, reg: Registration, to: str, subject: str, html: str,
             text: str, reply_to: str) -> bool:
    settings = get_settings()
    entry = EmailLog(registration_id=reg.id, kind=kind, to_email=to, subject=subject,
                     status="failed", provider=settings.mail_provider)
    db.add(entry)
    db.commit()  # gives the entry an id, used below as the idempotency key
    try:
        provider = get_provider(settings)
        provider_id = provider.send(
            Message(to=to, subject=subject, html=html, text=text, from_addr=settings.mail_from,
                    reply_to=reply_to, idempotency_key=f"regsite-email-{entry.id}")
        )
        entry.status, entry.provider_id = "sent", provider_id
    except MailError as exc:
        entry.error = str(exc)[:1000]
        log.error("email %s to %s failed: %s", kind, to, exc)
    except Exception as exc:  # never let an email problem crash a request
        entry.error = f"unexpected error: {exc}"[:1000]
        log.exception("email %s to %s crashed", kind, to)
    db.commit()
    return entry.status == "sent"


def send_student_received(registration_id: int) -> bool:
    """The 'we have received your registration' email to the student."""
    settings = get_settings()
    with SessionLocal() as db:
        reg = db.get(Registration, registration_id)
        if reg is None:
            return False
        subject, html, text = _build("received", reg)
        return _deliver(db, kind="received", reg=reg, to=reg.email, subject=subject, html=html,
                        text=text, reply_to=settings.mail_reply_to)


def send_registration_emails(registration_id: int) -> None:
    """Confirmation to the student and an alert to the trainer. Runs in a background task."""
    settings = get_settings()
    send_student_received(registration_id)
    with SessionLocal() as db:
        reg = db.get(Registration, registration_id)
        if reg is None:
            return
        subject, html, text = _build_alert(reg)
        _deliver(db, kind="admin_alert", reg=reg, to=settings.admin_alert_email, subject=subject,
                 html=html, text=text, reply_to=reg.email)


def send_decision_email(registration_id: int, kind: str, note: str = "") -> bool:
    """Tell the student about a decision (kind is approved, kiv or rejected)."""
    settings = get_settings()
    with SessionLocal() as db:
        reg = db.get(Registration, registration_id)
        if reg is None or kind not in COPY:
            return False
        subject, html, text = _build(kind, reg, note)
        return _deliver(db, kind=kind, reg=reg, to=reg.email, subject=subject, html=html, text=text,
                        reply_to=settings.mail_reply_to)
