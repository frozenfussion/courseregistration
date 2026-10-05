"""The registrations list: filter, search, approve / KIV / reject, email history and CSV export."""
import csv
import io
from collections import defaultdict
from datetime import timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.db import get_db
from app.formatting import fmt_dt, to_local
from app.models import (
    APPROVED,
    KIV,
    PENDING,
    REJECTED,
    STATUS_LABELS,
    STATUSES,
    Course,
    EmailLog,
    Registration,
    StatusLog,
    utcnow,
)
from app.modules.admin.common import render
from app.modules.mail import send_decision_email, send_student_received
from app.services import counts_by_status, seats_for
from app.templating import templates

router = APIRouter()

TABS = [("all", "All"), (PENDING, "Pending"), (APPROVED, "Approved"), (KIV, "KIV"), (REJECTED, "Rejected")]


def _courses(db: Session) -> list[Course]:
    return list(db.scalars(
        select(Course).order_by(Course.is_active.desc(), Course.start_date.desc().nulls_last(), Course.id.desc())
    ))


def _resolve_course(db: Session, course_id: int | None) -> Course | None:
    if course_id:
        found = db.get(Course, course_id)
        if found:
            return found
    courses = _courses(db)
    return courses[0] if courses else None  # active course sorts first


def _query(course_id: int, status: str, q: str):
    stmt = select(Registration).where(Registration.course_id == course_id)
    if status in STATUSES:
        stmt = stmt.where(Registration.status == status)
    q = q.strip()
    if q:
        like = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        stmt = stmt.where(or_(*[
            col.ilike(like, escape="\\")
            for col in (Registration.name, Registration.email, Registration.company,
                        Registration.phone, Registration.job_title)
        ]))
    return stmt.order_by(Registration.created_at.desc(), Registration.id.desc())


def _emails_for(db: Session, ids: list[int]) -> dict[int, list[EmailLog]]:
    grouped: dict[int, list[EmailLog]] = defaultdict(list)
    if ids:
        for e in db.scalars(select(EmailLog).where(EmailLog.registration_id.in_(ids)).order_by(EmailLog.id.desc())):
            grouped[e.registration_id].append(e)
    return grouped


def _failed_emails(db: Session, course_id: int) -> int:
    since = utcnow() - timedelta(days=7)
    return db.scalar(
        select(func.count(EmailLog.id))
        .join(Registration, Registration.id == EmailLog.registration_id)
        .where(Registration.course_id == course_id, EmailLog.status == "failed", EmailLog.created_at >= since)
    ) or 0


def _context(db: Session, course: Course | None, status: str, q: str) -> dict:
    status = status if status in STATUSES else "all"
    ctx = {"course": course, "status": status, "q": q, "tabs": TABS, "labels": STATUS_LABELS,
           "rows": [], "emails": {}, "counts": {}, "seats": None, "failed_emails": 0, "over_capacity": False}
    if course is None:
        return ctx
    rows = list(db.scalars(_query(course.id, status, q).options(selectinload(Registration.log))))
    seats = seats_for(db, course)
    ctx.update(
        rows=rows,
        emails=_emails_for(db, [r.id for r in rows]),
        counts=counts_by_status(db, course.id),
        seats=seats,
        failed_emails=_failed_emails(db, course.id),
        over_capacity=seats.capacity > 0 and seats.approved > seats.capacity,
    )
    return ctx


@router.get("/registrations", response_class=HTMLResponse)
def registrations(request: Request, db: Session = Depends(get_db), course_id: int | None = None,
                  status: str = "all", q: str = ""):
    course = _resolve_course(db, course_id)
    ctx = _context(db, course, status, q)
    if request.headers.get("hx-request") == "true" and request.headers.get("hx-target") == "table":
        return templates.TemplateResponse(request, "admin/_results.html", {**ctx, "oob": True})
    return render(request, db, "admin/registrations.html", "registrations", courses=_courses(db), **ctx)


@router.post("/registrations/{reg_id}/decision", response_class=HTMLResponse)
def decide(
    reg_id: int,
    request: Request,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    status: str = Form(...),
    note: str = Form(""),
    notify: str = Form(""),
    tab: str = Form("all"),
    q: str = Form(""),
):
    reg = db.get(Registration, reg_id)
    if reg is None:
        raise HTTPException(404)
    if status not in STATUSES:
        raise HTTPException(400, "Unknown status")

    note = note.strip()
    old = reg.status
    if status != old or note:
        emailing = bool(notify) and status != PENDING
        reg.status = status
        reg.decision_note = note if status != PENDING else ""
        reg.decided_at = None if status == PENDING else utcnow()
        db.add(StatusLog(registration_id=reg.id, from_status=old, to_status=status, note=note, notified=emailing))
        db.commit()
        if emailing:
            background.add_task(send_decision_email, reg.id, status, note)

    ctx = _context(db, reg.course, tab, q)
    visible = tab == "all" or tab not in STATUSES or reg.status == tab
    message = ""
    if ctx["over_capacity"]:
        message = (f"Over capacity: {ctx['seats'].approved} approved for {ctx['seats'].capacity} seats. "
                   "The registration was still approved.")
    return templates.TemplateResponse(
        request, "admin/_decision.html",
        {**ctx, "r": reg, "visible": visible, "oob": True, "notice": message,
         "emails": _emails_for(db, [reg.id])},
    )


@router.post("/registrations/{reg_id}/resend-email", response_class=HTMLResponse)
def resend_email(
    reg_id: int, request: Request, db: Session = Depends(get_db),
    tab: str = Form("all"), q: str = Form(""),
):
    """Send the email that matches the registration's current status again."""
    reg = db.get(Registration, reg_id)
    if reg is None:
        raise HTTPException(404)
    ok = send_student_received(reg.id) if reg.status == PENDING else send_decision_email(
        reg.id, reg.status, reg.decision_note)
    db.expire_all()
    ctx = _context(db, reg.course, tab, q)
    message = "Email sent." if ok else "The email could not be sent. See the email history below."
    return templates.TemplateResponse(
        request, "admin/_decision.html",
        {**ctx, "r": db.get(Registration, reg_id), "visible": True, "oob": True, "notice": message,
         "notice_kind": "ok" if ok else "bad", "emails": _emails_for(db, [reg_id])},
    )


@router.post("/registrations/{reg_id}/delete", response_class=HTMLResponse)
def delete_registration(
    reg_id: int, request: Request, db: Session = Depends(get_db),
    tab: str = Form("all"), q: str = Form(""),
):
    """Remove a registration for good (a test entry, or spam). Its decision log goes with it."""
    reg = db.get(Registration, reg_id)
    if reg is None:
        raise HTTPException(404)
    course = reg.course
    db.delete(reg)
    db.commit()
    ctx = _context(db, course, tab, q)
    return templates.TemplateResponse(
        request, "admin/_decision.html",
        {**ctx, "visible": False, "oob": True, "notice": "Registration deleted.", "notice_kind": "ok", "emails": {}},
    )


_FORMULA_START = ("=", "+", "-", "@", "\t", "\r")


def _csv_safe(value: str) -> str:
    """Stop spreadsheet programs from running a cell as a formula."""
    return "'" + value if value.startswith(_FORMULA_START) else value


@router.get("/registrations.csv")
def registrations_csv(db: Session = Depends(get_db), course_id: int | None = None,
                      status: str = "all", q: str = ""):
    course = _resolve_course(db, course_id)
    if course is None:
        raise HTTPException(404, "No course")
    status = status if status in STATUSES else "all"
    buf = io.StringIO()
    out = csv.writer(buf)
    out.writerow(["Course", "Status", "Name", "Email", "Phone", "Company", "Job title", "Notes",
                  "Submitted", "Decided", "Decision note", "Flagged"])
    for r in db.scalars(_query(course.id, status, q)):
        out.writerow([
            _csv_safe(course.title), STATUS_LABELS[r.status], _csv_safe(r.name), _csv_safe(r.email),
            r.phone, _csv_safe(r.company), _csv_safe(r.job_title), _csv_safe(r.notes),
            fmt_dt(r.created_at), fmt_dt(r.decided_at), _csv_safe(r.decision_note),
            r.flag_reason if r.flagged else "",
        ])
    stamp = to_local(utcnow()).strftime("%Y%m%d")
    name = f"registrations-{course.slug}-{status}-{stamp}.csv"
    # The byte-order mark makes Excel on Windows read names with accents correctly.
    return Response(
        content="﻿" + buf.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )
