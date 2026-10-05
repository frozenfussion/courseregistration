"""Public pages: the active course, the registration form and the brochure PDF."""
import re
from datetime import date

from email_validator import EmailNotValidError, validate_email
from fastapi import APIRouter, BackgroundTasks, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Registration
from app.modules.brochure import render_brochure
from app.modules.mail import send_registration_emails
from app.modules.spamcheck import FLAG, REJECT, Submission, run_checks
from app.security import form_token_age, ip_hash, make_form_token
from app.services import (
    get_active_course,
    get_site,
    registration_closed_reason,
    seats_for,
)
from app.templating import templates

router = APIRouter()

_PHONE = re.compile(r"^[0-9+()\-\s.]{7,25}$")


def _page_context(db: Session, *, state: str | None = None, values: dict | None = None,
                  errors: dict | None = None, form_error: str = "") -> dict:
    course = get_active_course(db)
    site = get_site(db)
    ctx = {
        "course": course,
        "site": site,
        "seats": None,
        "closed": None,
        "state": state or "form",
        "values": values or {},
        "errors": errors or {},
        "form_error": form_error,
        "form_token": make_form_token(),
    }
    if course:
        seats = seats_for(db, course)
        closed = registration_closed_reason(course, seats, date.today())
        ctx.update(seats=seats, closed=closed)
        if state in (None, "form") and closed:
            ctx["state"] = closed
    return ctx


@router.get("/", response_class=HTMLResponse)
def index(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse(request, "public/index.html", _page_context(db))


@router.get("/brochure.pdf")
def brochure(db: Session = Depends(get_db)):
    course = get_active_course(db)
    if course is None:
        raise HTTPException(status_code=404, detail="No programme is open for registration.")
    pdf = render_brochure(course, get_site(db))
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{course.slug}-brochure.pdf"'},
    )


_CONTROL = re.compile(r"[\x00-\x1f\x7f]+")


def _clean(value: str) -> str:
    """One-line fields: control characters (including line breaks) become a space."""
    return re.sub(r" {2,}", " ", _CONTROL.sub(" ", value)).strip()


def _validate(raw: dict) -> tuple[dict, dict]:
    """Return (cleaned values, errors)."""
    v = {
        "name": _clean(raw["name"]),
        "email": _clean(raw["email"]),
        "phone": _clean(raw["phone"]),
        "company": _clean(raw["company"]),
        "job_title": _clean(raw["job_title"]),
        "notes": raw["notes"].replace("\r", "").strip(),
        "consent": raw["consent"] == "yes",
    }
    errors: dict[str, str] = {}
    if len(v["name"]) < 2:
        errors["name"] = "Please enter your full name."
    elif len(v["name"]) > 120:
        errors["name"] = "That name is too long."
    try:
        v["email"] = validate_email(v["email"], check_deliverability=False).normalized
    except EmailNotValidError:
        errors["email"] = "Please enter a valid email address."
    digits = sum(c.isdigit() for c in v["phone"])
    if not _PHONE.match(v["phone"]) or digits < 7:
        errors["phone"] = "Please enter a valid phone number."
    if len(v["company"]) > 120:
        errors["company"] = "That is too long."
    if len(v["job_title"]) > 120:
        errors["job_title"] = "That is too long."
    if len(v["notes"]) > 1000:
        errors["notes"] = "Please keep notes under 1,000 characters."
    if not v["consent"]:
        errors["consent"] = "Please tick the box to continue."
    return v, errors


@router.post("/register", response_class=HTMLResponse)
def register(
    request: Request,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    name: str = Form(""),
    email: str = Form(""),
    phone: str = Form(""),
    company: str = Form(""),
    job_title: str = Form(""),
    notes: str = Form(""),
    consent: str = Form(""),
    website: str = Form(""),
    ft: str = Form(""),
):
    htmx = request.headers.get("hx-request") == "true"
    template = "public/_register_card.html" if htmx else "public/index.html"

    def respond(**kw):
        return templates.TemplateResponse(request, template, _page_context(db, **kw))

    course = get_active_course(db)
    if course is None:
        return respond(state="form") if not htmx else HTMLResponse("", status_code=204)

    seats = seats_for(db, course)
    closed = registration_closed_reason(course, seats, date.today())
    if closed:
        return respond(state=closed)

    raw = dict(name=name, email=email, phone=phone, company=company, job_title=job_title,
               notes=notes, consent=consent)
    values, errors = _validate(raw)
    shown = {**values, "consent": values["consent"]}
    if errors:
        return respond(state="form", values=shown, errors=errors)

    verdict = run_checks(
        Submission(
            name=values["name"], email=values["email"], phone=values["phone"],
            company=values["company"], job_title=values["job_title"], notes=values["notes"],
            honeypot=website, form_age_seconds=form_token_age(ft), ip_hash=ip_hash(request),
            course_id=course.id,
        ),
        db,
    )
    if verdict.action == REJECT:
        if verdict.silent:  # bots get a normal-looking answer and nothing is saved
            return respond(state="success")
        return respond(state="form", values=shown, form_error=verdict.user_message)

    email_key = values["email"].lower()
    duplicate_msg = {"email": "This email is already registered for this programme. If something "
                              "needs correcting, reply to your confirmation email."}
    if db.scalar(select(Registration.id).where(
            Registration.course_id == course.id, Registration.email_key == email_key)):
        return respond(state="form", values=shown, errors=duplicate_msg)

    reg = Registration(
        course_id=course.id, name=values["name"], email=values["email"], email_key=email_key,
        phone=values["phone"], company=values["company"], job_title=values["job_title"],
        notes=values["notes"], consent=True, ip_hash=ip_hash(request),
        flagged=verdict.action == FLAG, flag_reason="; ".join(verdict.reasons)[:300],
    )
    db.add(reg)
    try:
        db.commit()
    except IntegrityError:  # two submissions at the same instant
        db.rollback()
        return respond(state="form", values=shown, errors=duplicate_msg)

    background.add_task(send_registration_emails, reg.id)
    return respond(state="success")
