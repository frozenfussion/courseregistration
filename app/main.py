"""Application entry point: `uvicorn app.main:app`."""
import logging

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware

from app.config import assert_safe_for_production, get_settings
from app.db import engine
from app.modules.admin import router as admin_router
from app.modules.public import router as public_router
from app.security import CsrfError, NotAuthenticated
from app.templating import STATIC_DIR, templates

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

CSP = (
    "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
    "script-src 'self' 'unsafe-eval'; font-src 'self'; connect-src 'self'; "
    "frame-ancestors 'none'; form-action 'self'; base-uri 'self'; object-src 'none'"
)


def create_app() -> FastAPI:
    settings = get_settings()
    assert_safe_for_production(settings)

    app = FastAPI(title="Course registration", docs_url=None, redoc_url=None, openapi_url=None)

    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.secret_key,
        session_cookie="regsite_session",
        max_age=settings.session_hours * 3600,
        same_site="lax",
        https_only=settings.is_production,
    )

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response: Response = await call_next(request)
        h = response.headers
        h.setdefault("X-Content-Type-Options", "nosniff")
        h.setdefault("X-Frame-Options", "DENY")
        h.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        h.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        h.setdefault("Content-Security-Policy", CSP)
        if request.url.path.startswith("/admin"):
            h["Cache-Control"] = "no-store"
        return response

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    app.include_router(public_router)
    app.include_router(admin_router)

    @app.get("/healthz", include_in_schema=False)
    def healthz():
        with engine.connect() as conn:
            conn.execute(text("select 1"))
        return JSONResponse({"status": "ok"})

    @app.exception_handler(NotAuthenticated)
    async def _not_authenticated(request: Request, _exc: NotAuthenticated):
        if request.headers.get("hx-request") == "true":
            return Response(status_code=401, headers={"HX-Redirect": "/admin/login"})
        target = "/admin/login"
        if request.method == "GET" and request.url.path.startswith("/admin"):
            target += f"?next={request.url.path}"
        return RedirectResponse(target, status_code=303)

    @app.exception_handler(CsrfError)
    async def _csrf(request: Request, _exc: CsrfError):
        return HTMLResponse(
            "<h1>Session expired</h1><p>Please reload the page and try again.</p>", status_code=403
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException):
        if exc.status_code == 404 and "text/html" in request.headers.get("accept", ""):
            return templates.TemplateResponse(request, "error.html", {"code": 404}, status_code=404)
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code, headers=exc.headers)

    return app


app = create_app()
