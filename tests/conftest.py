import os
import re
import tempfile
import warnings

# Settings are read once, so point them at a throwaway database before the app is imported.
_TMP = tempfile.mkdtemp(prefix="regsite-test-")
os.environ.update(
    DATABASE_URL=f"sqlite:///{_TMP}/test.db",
    APP_ENV="test",
    MAIL_PROVIDER="console",
    SECRET_KEY="test-secret-key-that-is-long-enough-for-anything",
    BASE_URL="http://testserver",
    REGISTRATION_RATE_LIMIT="5",
    MIN_FORM_SECONDS="0",
)
warnings.filterwarnings("ignore")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import AdminUser, Course  # noqa: E402
from app.security import hash_password, make_form_token  # noqa: E402
from app.seed import seed_default_course  # noqa: E402
from app.services import activate_course  # noqa: E402

ADMIN_USER, ADMIN_PASSWORD = "tester", "a-long-test-password"


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield


@pytest.fixture
def db():
    with SessionLocal() as session:
        yield session


@pytest.fixture
def course(db) -> Course:
    return seed_default_course(db)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def admin(db) -> AdminUser:
    user = AdminUser(username=ADMIN_USER, password_hash=hash_password(ADMIN_PASSWORD))
    db.add(user)
    db.commit()
    return user


def csrf_from(html: str) -> str:
    return re.search(r'"X-CSRF-Token": "([^"]+)"', html).group(1)


@pytest.fixture
def admin_client(client, admin):
    """A client that is signed in. `client.csrf` holds the CSRF token for POSTs."""
    page = client.get("/admin/login")
    token = re.search(r'name="csrf_token" value="([^"]+)"', page.text).group(1)
    resp = client.post(
        "/admin/login",
        data={"username": ADMIN_USER, "password": ADMIN_PASSWORD, "csrf_token": token},
        follow_redirects=False,
    )
    assert resp.status_code == 303, resp.text
    client.csrf = csrf_from(client.get("/admin/courses/new").text)
    return client


def registration_form(**overrides) -> dict:
    data = {
        "name": "Aisyah Rahman",
        "email": "aisyah@example.com",
        "phone": "012 345 6789",
        "company": "Example Berhad",
        "job_title": "Engineer",
        "notes": "",
        "consent": "yes",
        "website": "",
        "ft": make_form_token(),
    }
    data.update(overrides)
    return data


@pytest.fixture
def make_course(db):
    def _make(title="Another Course", active=False, **kw) -> Course:
        from app.services import unique_slug

        c = Course(slug=unique_slug(db, title), title=title, capacity=kw.pop("capacity", 30), **kw)
        db.add(c)
        db.commit()
        if active:
            activate_course(db, c)
        return c

    return _make
