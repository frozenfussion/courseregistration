"""One shared Jinja environment for pages, emails and the brochure."""
from pathlib import Path

from fastapi.templating import Jinja2Templates
from markupsafe import Markup, escape

from app import formatting
from app.config import BASE_DIR, get_settings

TEMPLATE_DIR = BASE_DIR / "app" / "templates"
STATIC_DIR = BASE_DIR / "app" / "static"

templates = Jinja2Templates(directory=str(TEMPLATE_DIR))
env = templates.env


def static(path: str) -> str:
    """URL for a static file with a cache-busting version taken from the file's modified time."""
    file = Path(STATIC_DIR) / path
    version = int(file.stat().st_mtime) if file.exists() else 0
    return f"/static/{path}?v={version}"


def accent(title: str, word: str = "") -> Markup:
    """Escape the title and wrap the first occurrence of `word` in <em> (italic gold in the hero)."""
    safe = str(escape(title))
    w = str(escape(word or ""))
    if w and w in safe:
        safe = safe.replace(w, f"<em>{w}</em>", 1)
    return Markup(safe)


env.globals.update(
    static=static,
    TBA=formatting.TBA,
    base_url=lambda: get_settings().base_url.rstrip("/"),
)
env.filters.update(
    dt=formatting.fmt_dt,
    dt_short=formatting.fmt_dt_short,
    date_range=formatting.fmt_date_range,
    split_plus=formatting.split_plus,
    accent=accent,
)
