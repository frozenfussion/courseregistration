"""The downloadable brochure: a PDF built on request from the active course's own data."""
import base64
import hashlib
import io
import json
import logging
from collections import OrderedDict

import qrcode
import qrcode.image.svg
from weasyprint import HTML

from app.config import get_settings
from app.models import Course
from app.templating import STATIC_DIR, env

# WeasyPrint is chatty about CSS it does not support; keep the log readable.
logging.getLogger("weasyprint").setLevel(logging.ERROR)
logging.getLogger("fontTools").setLevel(logging.ERROR)

_CACHE: "OrderedDict[str, bytes]" = OrderedDict()
_CACHE_SIZE = 8


def _qr_data_uri(url: str) -> str:
    img = qrcode.make(url, image_factory=qrcode.image.svg.SvgPathImage, box_size=10, border=0)
    buf = io.BytesIO()
    img.save(buf)
    return "data:image/svg+xml;base64," + base64.b64encode(buf.getvalue()).decode()


def _cache_key(course: Course, site: dict, base: str) -> str:
    payload = json.dumps(
        [course.id, str(course.updated_at), site, base], sort_keys=True, default=str
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def render_brochure(course: Course, site: dict) -> bytes:
    base = get_settings().base_url.rstrip("/")
    key = _cache_key(course, site, base)
    if key in _CACHE:
        _CACHE.move_to_end(key)
        return _CACHE[key]

    html = env.get_template("brochure/brochure.html").render(
        course=course, site=site, page_url=base + "/", qr=_qr_data_uri(base + "/")
    )
    pdf = HTML(string=html, base_url=str(STATIC_DIR) + "/").write_pdf()

    _CACHE[key] = pdf
    while len(_CACHE) > _CACHE_SIZE:
        _CACHE.popitem(last=False)
    return pdf
