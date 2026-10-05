"""Course CMS: create, edit, duplicate, activate and delete courses."""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import APPROVED, Course, Registration
from app.modules.admin.common import flash, render
from app.services import activate_course, duplicate_course, unique_slug

router = APIRouter(prefix="/courses")

MAX_ITEMS = 60


def _courses_with_counts(db: Session) -> list[dict]:
    totals = dict(db.execute(select(Registration.course_id, func.count()).group_by(Registration.course_id)).all())
    approved = dict(db.execute(
        select(Registration.course_id, func.count()).where(Registration.status == APPROVED)
        .group_by(Registration.course_id)).all())
    courses = db.scalars(
        select(Course).order_by(Course.is_active.desc(), Course.start_date.desc().nulls_last(), Course.id.desc())
    )
    return [{"c": c, "total": totals.get(c.id, 0), "approved": approved.get(c.id, 0)} for c in courses]


def _form_from_course(c: Course | None) -> dict:
    if c is None:
        return {"title": "", "accent_word": "", "tagline": "", "introduction": "", "outcomes": [""],
                "prerequisites": [""], "audience": [""], "outline": [{"title": "", "topics": ""}],
                "duration_text": "", "start_date": "", "end_date": "", "daily_time": "", "venue": "",
                "map_url": "", "fee_text": "", "fee_note": "", "capacity": "30",
                "registration_deadline": "", "is_active": False}
    return {
        "title": c.title, "accent_word": c.accent_word, "tagline": c.tagline, "introduction": c.introduction,
        "outcomes": list(c.outcomes or []) or [""], "prerequisites": list(c.prerequisites or []) or [""],
        "audience": list(c.audience or []) or [""],
        "outline": [{"title": m.get("title", ""), "topics": "\n".join(m.get("topics", []))}
                    for m in (c.outline or [])] or [{"title": "", "topics": ""}],
        "duration_text": c.duration_text,
        "start_date": c.start_date.isoformat() if c.start_date else "",
        "end_date": c.end_date.isoformat() if c.end_date else "",
        "daily_time": c.daily_time, "venue": c.venue, "map_url": c.map_url,
        "fee_text": c.fee_text, "fee_note": c.fee_note, "capacity": str(c.capacity),
        "registration_deadline": c.registration_deadline.isoformat() if c.registration_deadline else "",
        "is_active": c.is_active,
    }


def _lines(values: list[str]) -> list[str]:
    return [v.strip() for v in values if v and v.strip()][:MAX_ITEMS]


def _parse_date(raw: str, label: str, errors: list[str]) -> date | None:
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        errors.append(f"{label} is not a valid date.")
        return None


async def _parse_form(request: Request) -> tuple[dict, dict, list[str]]:
    """Return (form for redisplay, clean values for the model, errors)."""
    f = await request.form()
    text = lambda k: str(f.get(k, "")).strip()  # noqa: E731
    titles, topics = f.getlist("module_title"), f.getlist("module_topics")
    outline_raw = [{"title": (t or "").strip(), "topics": (topics[i] if i < len(topics) else "")}
                   for i, t in enumerate(titles)]
    form = {
        "title": text("title"), "accent_word": text("accent_word"), "tagline": text("tagline"),
        "introduction": str(f.get("introduction", "")).replace("\r", "").strip(),
        "outcomes": f.getlist("outcomes") or [""], "prerequisites": f.getlist("prerequisites") or [""],
        "audience": f.getlist("audience") or [""], "outline": outline_raw or [{"title": "", "topics": ""}],
        "duration_text": text("duration_text"), "start_date": text("start_date"), "end_date": text("end_date"),
        "daily_time": text("daily_time"), "venue": text("venue"), "map_url": text("map_url"),
        "fee_text": text("fee_text"), "fee_note": text("fee_note"), "capacity": text("capacity"),
        "registration_deadline": text("registration_deadline"), "is_active": bool(f.get("is_active")),
    }
    errors: list[str] = []
    if not form["title"]:
        errors.append("The title is required.")
    try:
        capacity = int(form["capacity"])
        if not 1 <= capacity <= 10000:
            raise ValueError
    except ValueError:
        capacity = 30
        errors.append("Capacity must be a whole number between 1 and 10,000.")
    start = _parse_date(form["start_date"], "Start date", errors)
    end = _parse_date(form["end_date"], "End date", errors)
    deadline = _parse_date(form["registration_deadline"], "Registration deadline", errors)
    if start and end and end < start:
        errors.append("The end date is before the start date.")
    if form["map_url"] and not form["map_url"].startswith(("https://", "http://")):
        errors.append("The map link must start with https://")

    outline = [{"title": m["title"], "topics": _lines(m["topics"].replace("\r", "").split("\n"))}
               for m in outline_raw if m["title"]][:MAX_ITEMS]
    clean = {
        "title": form["title"][:200], "accent_word": form["accent_word"][:80], "tagline": form["tagline"][:400],
        "introduction": form["introduction"], "outcomes": _lines(form["outcomes"]),
        "prerequisites": _lines(form["prerequisites"]), "audience": _lines(form["audience"]),
        "outline": outline, "duration_text": form["duration_text"][:80], "start_date": start,
        "end_date": end, "daily_time": form["daily_time"][:80], "venue": form["venue"][:200],
        "map_url": form["map_url"][:400], "fee_text": form["fee_text"][:120], "fee_note": form["fee_note"][:120],
        "capacity": capacity, "registration_deadline": deadline,
    }
    return form, clean, errors


def _editor(request, db, course: Course | None, form: dict, errors: list[str], status_code: int = 200):
    return render(
        request, db, "admin/courses.html", "courses", status_code=status_code,
        items=_courses_with_counts(db), course=course, f=form, errors=errors,
        reg_total=len(course.registrations) if course else 0,
    )


@router.get("", response_class=HTMLResponse)
def courses_home(db: Session = Depends(get_db)):
    first = db.scalar(select(Course).order_by(Course.is_active.desc(), Course.id.desc()))
    return RedirectResponse(f"/admin/courses/{first.id}" if first else "/admin/courses/new", status_code=303)


@router.get("/new", response_class=HTMLResponse)
def new_course(request: Request, db: Session = Depends(get_db)):
    return _editor(request, db, None, _form_from_course(None), [])


@router.post("/new", response_class=HTMLResponse)
async def create_course(request: Request, db: Session = Depends(get_db)):
    form, clean, errors = await _parse_form(request)
    if errors:
        return _editor(request, db, None, form, errors, 422)
    course = Course(slug=unique_slug(db, clean["title"]), is_active=False, **clean)
    db.add(course)
    db.commit()
    if form["is_active"]:
        activate_course(db, course)
    flash(request, "Course created.")
    return RedirectResponse(f"/admin/courses/{course.id}", status_code=303)


@router.get("/{course_id}", response_class=HTMLResponse)
def edit_course(course_id: int, request: Request, db: Session = Depends(get_db)):
    course = db.get(Course, course_id)
    if course is None:
        raise HTTPException(404)
    return _editor(request, db, course, _form_from_course(course), [])


@router.post("/{course_id}", response_class=HTMLResponse)
async def save_course(course_id: int, request: Request, db: Session = Depends(get_db)):
    course = db.get(Course, course_id)
    if course is None:
        raise HTTPException(404)
    form, clean, errors = await _parse_form(request)
    if errors:
        return _editor(request, db, course, form, errors, 422)
    for key, value in clean.items():
        setattr(course, key, value)
    db.commit()
    if form["is_active"] and not course.is_active:
        activate_course(db, course)
    elif not form["is_active"] and course.is_active:
        course.is_active = False
        db.commit()
    flash(request, "Saved.")
    return RedirectResponse(f"/admin/courses/{course.id}", status_code=303)


@router.post("/{course_id}/duplicate")
def duplicate(course_id: int, request: Request, db: Session = Depends(get_db)):
    course = db.get(Course, course_id)
    if course is None:
        raise HTTPException(404)
    copy = duplicate_course(db, course)
    flash(request, "Duplicated. Set the new dates, then make it active when you are ready.")
    return RedirectResponse(f"/admin/courses/{copy.id}", status_code=303)


@router.post("/{course_id}/activate")
def activate(course_id: int, request: Request, db: Session = Depends(get_db)):
    course = db.get(Course, course_id)
    if course is None:
        raise HTTPException(404)
    activate_course(db, course)
    flash(request, f"“{course.title}” is now the active course. All other courses are inactive.")
    return RedirectResponse(f"/admin/courses/{course.id}", status_code=303)


@router.post("/{course_id}/deactivate")
def deactivate(course_id: int, request: Request, db: Session = Depends(get_db)):
    course = db.get(Course, course_id)
    if course is None:
        raise HTTPException(404)
    course.is_active = False
    db.commit()
    flash(request, "Deactivated. The public page now shows that no programme is open.")
    return RedirectResponse(f"/admin/courses/{course.id}", status_code=303)


@router.post("/{course_id}/delete")
def delete(course_id: int, request: Request, db: Session = Depends(get_db)):
    course = db.get(Course, course_id)
    if course is None:
        raise HTTPException(404)
    if db.scalar(select(func.count()).where(Registration.course_id == course.id)):
        flash(request, "This course has registrations, so it cannot be deleted. Deactivate it instead.", "bad")
        return RedirectResponse(f"/admin/courses/{course.id}", status_code=303)
    db.delete(course)
    db.commit()
    flash(request, "Course deleted.")
    return RedirectResponse("/admin/courses", status_code=303)
