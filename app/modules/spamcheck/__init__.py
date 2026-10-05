"""Registration abuse checks.

Every submission passes through `run_checks` before it is saved. Each checker returns a verdict:

    accept  - nothing suspicious
    flag    - save it, but mark it for the admin's attention (shown as a badge)
    reject  - do not save it

This is the single place to plug in a smarter check later (for example a small language model
that reads the notes field). Write a class with a `name` and a `check(submission, db)` method that
returns a `Verdict`, then add it to `DEFAULT_CHECKERS`.
"""
import re
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Protocol

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Registration, utcnow

ACCEPT, FLAG, REJECT = "accept", "flag", "reject"


@dataclass
class Submission:
    name: str
    email: str
    phone: str
    company: str = ""
    job_title: str = ""
    notes: str = ""
    honeypot: str = ""  # a hidden field real people never fill in
    form_age_seconds: int | None = None  # None means the form token was missing or invalid
    ip_hash: str = ""
    course_id: int = 0


@dataclass
class Verdict:
    action: str = ACCEPT
    reason: str = ""
    silent: bool = False  # reject without telling the sender why (used for bots)
    user_message: str = ""  # shown to a human when rejected loudly


@dataclass
class Result:
    action: str = ACCEPT
    reasons: list[str] = field(default_factory=list)
    silent: bool = False
    user_message: str = ""


class Checker(Protocol):
    name: str

    def check(self, sub: Submission, db: Session) -> Verdict: ...


class Honeypot:
    name = "honeypot"

    def check(self, sub: Submission, db: Session) -> Verdict:
        if sub.honeypot.strip():
            return Verdict(REJECT, "hidden field filled", silent=True)
        return Verdict()


class FormTiming:
    name = "form-timing"

    def check(self, sub: Submission, db: Session) -> Verdict:
        if sub.form_age_seconds is None:
            return Verdict(REJECT, "missing or invalid form token", silent=True)
        if sub.form_age_seconds < get_settings().min_form_seconds:
            return Verdict(FLAG, f"submitted {sub.form_age_seconds}s after the page loaded")
        return Verdict()


class RateLimit:
    name = "rate-limit"

    def check(self, sub: Submission, db: Session) -> Verdict:
        settings = get_settings()
        if not sub.ip_hash:
            return Verdict()
        since = utcnow() - timedelta(hours=1)
        recent = db.scalar(
            select(func.count()).where(
                Registration.ip_hash == sub.ip_hash, Registration.created_at >= since
            )
        )
        if (recent or 0) >= settings.registration_rate_limit:
            return Verdict(
                REJECT,
                "too many registrations from one network in an hour",
                user_message="Too many registrations were sent from your network recently. "
                "Please try again in an hour, or contact the trainer directly.",
            )
        return Verdict()


class LinkSpam:
    name = "link-spam"
    _url = re.compile(r"https?://|www\.", re.I)

    def check(self, sub: Submission, db: Session) -> Verdict:
        text = " ".join([sub.name, sub.company, sub.job_title, sub.notes])
        if len(self._url.findall(text)) >= 2:
            return Verdict(FLAG, "contains several links")
        return Verdict()


DEFAULT_CHECKERS: list[Checker] = [Honeypot(), FormTiming(), RateLimit(), LinkSpam()]


def run_checks(sub: Submission, db: Session, checkers: list[Checker] | None = None) -> Result:
    result = Result()
    for checker in checkers or DEFAULT_CHECKERS:
        verdict = checker.check(sub, db)
        if verdict.action == REJECT:
            return Result(REJECT, [verdict.reason], verdict.silent, verdict.user_message)
        if verdict.action == FLAG:
            result.action = FLAG
            result.reasons.append(verdict.reason)
    return result
