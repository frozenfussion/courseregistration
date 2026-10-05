"""Database models.

All datetimes are stored as naive UTC. Display code converts to the configured timezone.
"""
from datetime import date, datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

PENDING, APPROVED, KIV, REJECTED = "pending", "approved", "kiv", "rejected"
STATUSES = (PENDING, APPROVED, KIV, REJECTED)
STATUS_LABELS = {PENDING: "Pending", APPROVED: "Approved", KIV: "KIV", REJECTED: "Rejected"}


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Course(Base):
    __tablename__ = "courses"
    __table_args__ = (
        # At most one active course at any time (enforced by the database itself).
        Index("uq_courses_one_active", "is_active", unique=True, sqlite_where=text("is_active = 1")),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(160), unique=True)
    title: Mapped[str] = mapped_column(String(200))
    accent_word: Mapped[str] = mapped_column(String(80), default="")  # word in the title shown in italic gold
    tagline: Mapped[str] = mapped_column(String(400), default="")
    introduction: Mapped[str] = mapped_column(Text, default="")
    outcomes: Mapped[list] = mapped_column(JSON, default=list)
    prerequisites: Mapped[list] = mapped_column(JSON, default=list)
    audience: Mapped[list] = mapped_column(JSON, default=list)
    # [{"title": str, "topics": [str, ...]}, ...]
    outline: Mapped[list] = mapped_column(JSON, default=list)

    duration_text: Mapped[str] = mapped_column(String(80), default="")
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    daily_time: Mapped[str] = mapped_column(String(80), default="")
    venue: Mapped[str] = mapped_column(String(200), default="")
    map_url: Mapped[str] = mapped_column(String(400), default="")
    fee_text: Mapped[str] = mapped_column(String(120), default="")
    fee_note: Mapped[str] = mapped_column(String(120), default="")
    capacity: Mapped[int] = mapped_column(Integer, default=30)
    registration_deadline: Mapped[date | None] = mapped_column(Date, nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    registrations: Mapped[list["Registration"]] = relationship(
        back_populates="course", cascade="all, delete-orphan"
    )


class Registration(Base):
    __tablename__ = "registrations"
    __table_args__ = (UniqueConstraint("course_id", "email_key", name="uq_registration_course_email"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(254))
    email_key: Mapped[str] = mapped_column(String(254))  # lower-cased, used for duplicate checks
    phone: Mapped[str] = mapped_column(String(40))
    company: Mapped[str] = mapped_column(String(120), default="")
    job_title: Mapped[str] = mapped_column(String(120), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    consent: Mapped[bool] = mapped_column(Boolean, default=False)

    status: Mapped[str] = mapped_column(String(16), default=PENDING, index=True)
    decision_note: Mapped[str] = mapped_column(Text, default="")
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    flagged: Mapped[bool] = mapped_column(Boolean, default=False)
    flag_reason: Mapped[str] = mapped_column(String(300), default="")
    ip_hash: Mapped[str] = mapped_column(String(32), default="", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

    course: Mapped[Course] = relationship(back_populates="registrations")
    log: Mapped[list["StatusLog"]] = relationship(
        back_populates="registration", cascade="all, delete-orphan", order_by="StatusLog.id.desc()"
    )


class StatusLog(Base):
    """Every decision, so a disputed outcome can be traced."""

    __tablename__ = "status_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    registration_id: Mapped[int] = mapped_column(
        ForeignKey("registrations.id", ondelete="CASCADE"), index=True
    )
    from_status: Mapped[str] = mapped_column(String(16))
    to_status: Mapped[str] = mapped_column(String(16))
    note: Mapped[str] = mapped_column(Text, default="")
    notified: Mapped[bool] = mapped_column(Boolean, default=False)
    at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    registration: Mapped[Registration] = relationship(back_populates="log")


class EmailLog(Base):
    __tablename__ = "email_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    registration_id: Mapped[int | None] = mapped_column(
        ForeignKey("registrations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    kind: Mapped[str] = mapped_column(String(32))
    to_email: Mapped[str] = mapped_column(String(254))
    subject: Mapped[str] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(16))  # sent | failed
    error: Mapped[str] = mapped_column(Text, default="")
    provider: Mapped[str] = mapped_column(String(32), default="")
    provider_id: Mapped[str] = mapped_column(String(120), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class AdminUser(Base):
    __tablename__ = "admin_users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(60), unique=True)
    password_hash: Mapped[str] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class LoginAttempt(Base):
    __tablename__ = "login_attempts"

    id: Mapped[int] = mapped_column(primary_key=True)
    ip_hash: Mapped[str] = mapped_column(String(32), index=True)
    success: Mapped[bool] = mapped_column(Boolean, default=False)
    at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class SiteSetting(Base):
    """Key/value JSON store for editable site content (trainer highlights etc.)."""

    __tablename__ = "site_settings"

    key: Mapped[str] = mapped_column(String(60), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON, default=dict)
