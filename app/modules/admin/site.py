"""Site content: the trainer highlights shown on the public page and in the brochure."""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.modules.admin.common import flash, render
from app.services import SITE_DEFAULTS, get_site, save_site

router = APIRouter(prefix="/site")


@router.get("", response_class=HTMLResponse)
def site_page(request: Request, db: Session = Depends(get_db)):
    return render(request, db, "admin/site.html", "site", s=get_site(db), errors=[])


@router.post("", response_class=HTMLResponse)
async def save(request: Request, db: Session = Depends(get_db)):
    f = await request.form()
    text = lambda k, n=300: str(f.get(k, "")).strip()[:n]  # noqa: E731
    values, labels = f.getlist("stat_value"), f.getlist("stat_label")
    stats = [
        {"value": v.strip()[:20], "label": (labels[i] if i < len(labels) else "").strip()[:60]}
        for i, v in enumerate(values) if v.strip()
    ][:8]
    data = {
        "trainer_name": text("trainer_name", 80), "trainer_role": text("trainer_role", 120),
        "trainer_location": text("trainer_location", 80), "trainer_headline": text("trainer_headline", 160),
        "trainer_bio": text("trainer_bio", 1500),
        "credentials": [c.strip()[:80] for c in f.getlist("credentials") if c.strip()][:12],
        "stats": stats, "website_url": text("website_url", 200), "contact_email": text("contact_email", 200),
    }
    errors = []
    if not data["trainer_name"]:
        errors.append("The trainer name is required.")
    if data["website_url"] and not data["website_url"].startswith(("https://", "http://")):
        errors.append("The website link must start with https://")
    if errors:
        merged = {**SITE_DEFAULTS, **{k: v for k, v in data.items()}}
        return render(request, db, "admin/site.html", "site", status_code=422, s=merged, errors=errors)
    save_site(db, data)
    flash(request, "Saved.")
    return RedirectResponse("/admin/site", status_code=303)
