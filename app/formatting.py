"""Display helpers shared by templates, emails and the brochure."""
import re
from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.config import get_settings

TBA = "To be announced"


def tz() -> ZoneInfo:
    return ZoneInfo(get_settings().timezone)


def to_local(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    from datetime import timezone

    return dt.replace(tzinfo=timezone.utc).astimezone(tz())


def fmt_dt(dt: datetime | None) -> str:
    local = to_local(dt)
    return f"{local.day} {local:%b %Y}, {local:%H:%M}" if local else ""


def fmt_dt_short(dt: datetime | None) -> str:
    local = to_local(dt)
    return f"{local.day} {local:%b}, {local:%H:%M}" if local else ""


def fmt_date(d: date | None) -> str:
    return f"{d.day} {d:%B %Y}" if d else ""


def fmt_date_range(start: date | None, end: date | None) -> str:
    """'12 – 13 November 2026', '30 Nov – 1 December 2026', or the TBA text."""
    if not start and not end:
        return TBA
    if start and (not end or end == start):
        return fmt_date(start)
    if not start:
        return fmt_date(end)
    if (start.year, start.month) == (end.year, end.month):
        return f"{start.day} – {end.day} {end:%B %Y}"
    if start.year == end.year:
        return f"{start.day} {start:%B} – {end.day} {end:%B %Y}"
    return f"{fmt_date(start)} – {fmt_date(end)}"


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:120] or "course"


def split_plus(value: str) -> tuple[str, str]:
    """'10,000+' -> ('10,000', '+') so the plus sign can be styled separately."""
    value = (value or "").strip()
    if value.endswith("+"):
        return value[:-1], "+"
    return value, ""
