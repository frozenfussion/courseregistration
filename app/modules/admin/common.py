"""Helpers shared by the admin pages."""
from fastapi import Request
from sqlalchemy.orm import Session

from app.security import csrf_token
from app.services import pending_count
from app.templating import templates


def flash(request: Request, message: str, kind: str = "ok") -> None:
    """Show a one-time message on the next admin page."""
    request.session["flash"] = {"m": message, "k": kind}


def render(request: Request, db: Session, name: str, nav: str, status_code: int = 200, **ctx):
    ctx.update(
        nav=nav,
        csrf_token=csrf_token(request),
        flash=request.session.pop("flash", None),
        admin_name=request.session.get("admin_name", ""),
        pending_total=pending_count(db),
    )
    return templates.TemplateResponse(request, name, ctx, status_code=status_code)
