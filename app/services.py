"""Queries and small business rules shared by the public and admin modules."""
from dataclasses import dataclass
from datetime import date

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.formatting import slugify
from app.models import APPROVED, PENDING, STATUSES, Course, Registration, SiteSetting

SITE_KEY = "site"

SITE_DEFAULTS = {
    "trainer_name": "Faysal Aziz",
    "trainer_role": "Technology Trainer & Consultant",
    "trainer_location": "Kuala Lumpur",
    "trainer_headline": "Practical implementation, not theory alone.",
    "trainer_bio": (
        "Faysal Aziz has spent over 30 years across software engineering, systems architecture, "
        "cloud platforms, cybersecurity, automation and artificial intelligence, working with "
        "corporations, government agencies and financial institutions. His training is hands-on and "
        "built on real case studies from systems he has founded, architected and delivered."
    ),
    "credentials": [
        "HRDC Accredited Trainer",
        "Certified AI Expert",
        "Frost & Sullivan Excellence Award",
        "ITEX Best Corporate Invention",
    ],
    "stats": [
        {"value": "10,000+", "label": "Training hours"},
        {"value": "32+", "label": "Project implementations"},
        {"value": "11+", "label": "Countries"},
        {"value": "13+", "label": "Times Best Trainer"},
        {"value": "30+", "label": "Years of experience"},
    ],
    "website_url": "https://faysalaziz.com",
    "contact_email": "faysalabdulaziz@gmail.com",
}


def get_site(db: Session) -> dict:
    row = db.get(SiteSetting, SITE_KEY)
    data = dict(SITE_DEFAULTS)
    if row and isinstance(row.value, dict):
        data.update({k: v for k, v in row.value.items() if v not in (None, "")})
    return data


def save_site(db: Session, data: dict) -> None:
    row = db.get(SiteSetting, SITE_KEY)
    if row is None:
        db.add(SiteSetting(key=SITE_KEY, value=data))
    else:
        row.value = data
    db.commit()


def get_active_course(db: Session) -> Course | None:
    return db.scalar(select(Course).where(Course.is_active.is_(True)))


def counts_by_status(db: Session, course_id: int) -> dict[str, int]:
    rows = db.execute(
        select(Registration.status, func.count())
        .where(Registration.course_id == course_id)
        .group_by(Registration.status)
    ).all()
    counts = {s: 0 for s in STATUSES}
    counts.update({status: n for status, n in rows})
    counts["all"] = sum(counts[s] for s in STATUSES)
    return counts


def approved_count(db: Session, course_id: int) -> int:
    return db.scalar(
        select(func.count()).where(
            Registration.course_id == course_id, Registration.status == APPROVED
        )
    ) or 0


@dataclass
class Seats:
    capacity: int
    approved: int

    @property
    def left(self) -> int:
        return max(self.capacity - self.approved, 0)

    @property
    def is_full(self) -> bool:
        return self.capacity > 0 and self.approved >= self.capacity

    @property
    def percent(self) -> int:
        if self.capacity <= 0:
            return 0
        return min(100, round(self.approved / self.capacity * 100))

    @property
    def text(self) -> str:
        if self.is_full:
            return "Fully booked"
        return f"{self.left} of {self.capacity} seats left"


def seats_for(db: Session, course: Course) -> Seats:
    return Seats(capacity=course.capacity, approved=approved_count(db, course.id))


def registration_closed_reason(course: Course, seats: Seats, today: date | None = None) -> str | None:
    """None when registration is open, otherwise 'full' or 'deadline'."""
    if seats.is_full:
        return "full"
    today = today or date.today()
    if course.registration_deadline and today > course.registration_deadline:
        return "deadline"
    return None


def activate_course(db: Session, course: Course) -> None:
    """Make `course` the one active course. Done as two statements so the unique index holds."""
    db.execute(update(Course).where(Course.id != course.id).values(is_active=False))
    course.is_active = True
    db.commit()


def unique_slug(db: Session, title: str, exclude_id: int | None = None) -> str:
    base = slugify(title)
    slug, n = base, 2
    while True:
        existing = db.scalar(select(Course.id).where(Course.slug == slug))
        if existing is None or existing == exclude_id:
            return slug
        slug = f"{base}-{n}"
        n += 1


def duplicate_course(db: Session, source: Course) -> Course:
    copy = Course(
        slug=unique_slug(db, f"{source.title} copy"),
        title=f"{source.title} (copy)",
        accent_word=source.accent_word,
        tagline=source.tagline,
        introduction=source.introduction,
        outcomes=list(source.outcomes or []),
        prerequisites=list(source.prerequisites or []),
        audience=list(source.audience or []),
        outline=[dict(m, topics=list(m.get("topics", []))) for m in (source.outline or [])],
        duration_text=source.duration_text,
        start_date=None,
        end_date=None,
        daily_time=source.daily_time,
        venue=source.venue,
        map_url=source.map_url,
        fee_text=source.fee_text,
        fee_note=source.fee_note,
        capacity=source.capacity,
        registration_deadline=None,
        is_active=False,
    )
    db.add(copy)
    db.commit()
    return copy


def pending_count(db: Session) -> int:
    return db.scalar(select(func.count()).where(Registration.status == PENDING)) or 0
