"""Passwords, sessions, CSRF tokens and the signed public-form token."""
import hashlib
import hmac
import secrets
import time
from datetime import timedelta

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Depends, Request
from itsdangerous import BadSignature, URLSafeTimedSerializer
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import AdminUser, LoginAttempt, utcnow

_hasher = PasswordHasher()
# Used to keep login timing the same whether or not the username exists.
_DUMMY_HASH = _hasher.hash("not-a-real-password")


# ---------------------------------------------------------------- passwords
def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def burn_login_time() -> None:
    verify_password(_DUMMY_HASH, "wrong")


# ---------------------------------------------------------------- client identity
def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def ip_hash(request: Request) -> str:
    """Keyed hash of the address: usable for rate limits without storing the address itself."""
    key = get_settings().secret_key.encode()
    return hmac.new(key, client_ip(request).encode(), hashlib.sha256).hexdigest()[:32]


# ---------------------------------------------------------------- public form token
def _form_serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(get_settings().secret_key, salt="public-form-v1")


def make_form_token() -> str:
    return _form_serializer().dumps(int(time.time()))


def form_token_age(token: str) -> int | None:
    """Seconds since the form was rendered, or None if the token is missing, forged or stale."""
    try:
        issued = _form_serializer().loads(token, max_age=60 * 60 * 24)
    except (BadSignature, TypeError):
        return None
    return max(int(time.time()) - int(issued), 0)


# ---------------------------------------------------------------- admin CSRF
def csrf_token(request: Request) -> str:
    token = request.session.get("csrf")
    if not token:
        token = secrets.token_urlsafe(32)
        request.session["csrf"] = token
    return token


class CsrfError(Exception):
    pass


async def verify_csrf(request: Request) -> None:
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return
    expected = request.session.get("csrf")
    supplied = request.headers.get("x-csrf-token")
    if not supplied:
        form = await request.form()
        supplied = form.get("csrf_token")
    if not expected or not supplied or not secrets.compare_digest(str(supplied), expected):
        raise CsrfError()


# ---------------------------------------------------------------- admin auth
class NotAuthenticated(Exception):
    pass


def current_admin(request: Request, db: Session = Depends(get_db)) -> AdminUser:
    admin_id = request.session.get("admin_id")
    admin = db.get(AdminUser, admin_id) if admin_id else None
    if admin is None:
        raise NotAuthenticated()
    return admin


def too_many_login_attempts(db: Session, iph: str) -> bool:
    settings = get_settings()
    since = utcnow() - timedelta(minutes=settings.login_window_minutes)
    failures = db.scalar(
        select(func.count()).where(
            LoginAttempt.ip_hash == iph, LoginAttempt.success.is_(False), LoginAttempt.at >= since
        )
    )
    return (failures or 0) >= settings.login_max_attempts


def record_login_attempt(db: Session, iph: str, success: bool) -> None:
    db.add(LoginAttempt(ip_hash=iph, success=success))
    db.commit()
