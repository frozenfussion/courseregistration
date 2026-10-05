"""Admin area: login, registrations, course CMS and site content."""
from fastapi import APIRouter, Depends
from fastapi.responses import RedirectResponse

from app.modules.admin import auth, courses, registrations, site
from app.security import current_admin, verify_csrf

router = APIRouter()
router.include_router(auth.router)


@router.get("/admin", include_in_schema=False)
def admin_home():
    return RedirectResponse("/admin/registrations", status_code=303)



# Everything below requires a signed-in admin, and every POST must carry the CSRF token.
protected = APIRouter(prefix="/admin", dependencies=[Depends(current_admin), Depends(verify_csrf)])
protected.include_router(registrations.router)
protected.include_router(courses.router)
protected.include_router(site.router)
router.include_router(protected)
