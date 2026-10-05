"""Admin sign-in and sign-out (a single username and password, no MFA)."""
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import AdminUser, utcnow
from app.security import (
    burn_login_time,
    csrf_token,
    ip_hash,
    record_login_attempt,
    too_many_login_attempts,
    verify_csrf,
    verify_password,
)
from app.templating import templates

router = APIRouter(prefix="/admin")


def _safe_next(target: str) -> str:
    """Only allow redirects to other admin pages (blocks open redirects)."""
    if target.startswith("/admin") and not target.startswith("//") and "\\" not in target:
        return target
    return "/admin/registrations"


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request, next: str = ""):
    if request.session.get("admin_id"):
        return RedirectResponse("/admin/registrations", status_code=303)
    return templates.TemplateResponse(
        request, "admin/login.html", {"csrf_token": csrf_token(request), "next": next, "error": ""}
    )


@router.post("/login", response_class=HTMLResponse, dependencies=[Depends(verify_csrf)])
def login(
    request: Request,
    db: Session = Depends(get_db),
    username: str = Form(""),
    password: str = Form(""),
    next: str = Form(""),
):
    iph = ip_hash(request)

    def fail(message: str, status: int):
        return templates.TemplateResponse(
            request,
            "admin/login.html",
            {"csrf_token": csrf_token(request), "next": next, "error": message, "username": username},
            status_code=status,
        )

    if too_many_login_attempts(db, iph):
        return fail("Too many failed attempts. Please wait a few minutes and try again.", 429)

    admin = db.scalar(select(AdminUser).where(AdminUser.username == username.strip()))
    ok = False
    if admin is not None:
        ok = verify_password(admin.password_hash, password)
    else:
        burn_login_time()
    record_login_attempt(db, iph, ok)
    if not ok:
        return fail("Incorrect username or password.", 401)

    admin.last_login_at = utcnow()
    db.commit()
    request.session.clear()  # start a fresh session on sign-in
    request.session["admin_id"] = admin.id
    request.session["admin_name"] = admin.username
    return RedirectResponse(_safe_next(next), status_code=303)


@router.post("/logout", dependencies=[Depends(verify_csrf)])
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/admin/login", status_code=303)
