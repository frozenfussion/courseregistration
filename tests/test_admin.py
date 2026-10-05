import re

import pytest
from sqlalchemy import select

from app.models import Course, EmailLog, Registration, StatusLog
from tests.conftest import ADMIN_PASSWORD, ADMIN_USER, csrf_from


def add_reg(db, course, name="Student One", email="one@example.com", status="pending", **kw):
    reg = Registration(course_id=course.id, name=name, email=email, email_key=email.lower(),
                       phone="0123456789", status=status, consent=True, **kw)
    db.add(reg)
    db.commit()
    return reg


# ---------------------------------------------------------------- authentication
@pytest.mark.parametrize("path", ["/admin/registrations", "/admin/courses", "/admin/site",
                                  "/admin/registrations.csv"])
def test_admin_pages_require_login(client, path):
    r = client.get(path, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/admin/login")


def test_htmx_request_without_login_gets_a_redirect_header(client):
    r = client.get("/admin/registrations", headers={"HX-Request": "true"})
    assert r.status_code == 401 and r.headers["hx-redirect"] == "/admin/login"


def _login(client, username, password):
    page = client.get("/admin/login")
    token = re.search(r'name="csrf_token" value="([^"]+)"', page.text).group(1)
    return client.post("/admin/login", data={"username": username, "password": password,
                                             "csrf_token": token}, follow_redirects=False)


def test_login_success_and_wrong_password(client, admin):
    assert _login(client, ADMIN_USER, "wrong").status_code == 401
    ok = _login(client, ADMIN_USER, ADMIN_PASSWORD)
    assert ok.status_code == 303 and ok.headers["location"] == "/admin/registrations"
    assert client.get("/admin/registrations").status_code == 200


def test_login_does_not_reveal_whether_the_user_exists(client, admin):
    a = _login(client, "nobody", "whatever-password")
    b = _login(client, ADMIN_USER, "whatever-password")
    assert a.status_code == b.status_code == 401
    assert "Incorrect username or password." in a.text and "Incorrect username or password." in b.text


def test_login_is_throttled_after_repeated_failures(client, admin):
    for _ in range(5):
        assert _login(client, ADMIN_USER, "wrong").status_code == 401
    blocked = _login(client, ADMIN_USER, ADMIN_PASSWORD)  # even the right password is refused for a while
    assert blocked.status_code == 429


def test_login_requires_csrf_token(client, admin):
    client.get("/admin/login")
    r = client.post("/admin/login", data={"username": ADMIN_USER, "password": ADMIN_PASSWORD})
    assert r.status_code == 403


def test_login_next_is_restricted_to_admin_pages(client, admin):
    page = client.get("/admin/login")
    token = re.search(r'name="csrf_token" value="([^"]+)"', page.text).group(1)
    r = client.post("/admin/login", data={"username": ADMIN_USER, "password": ADMIN_PASSWORD,
                                          "csrf_token": token, "next": "https://evil.example/"},
                    follow_redirects=False)
    assert r.headers["location"] == "/admin/registrations"


def test_posts_without_csrf_token_are_refused(admin_client, course):
    r = admin_client.post(f"/admin/courses/{course.id}/duplicate")
    assert r.status_code == 403


def test_logout(admin_client):
    r = admin_client.post("/admin/logout", data={"csrf_token": admin_client.csrf}, follow_redirects=False)
    assert r.status_code == 303
    assert admin_client.get("/admin/registrations", follow_redirects=False).status_code == 303


# ---------------------------------------------------------------- registrations
def decide(client, reg, status, **extra):
    return client.post(f"/admin/registrations/{reg.id}/decision",
                       data={"status": status, "notify": "1", **extra},
                       headers={"HX-Request": "true", "X-CSRF-Token": client.csrf})


def test_approve_then_change_mind_and_every_step_is_logged(admin_client, course, db):
    reg = add_reg(db, course)
    assert decide(admin_client, reg, "approved").status_code == 200
    assert decide(admin_client, reg, "kiv", note="Let us talk").status_code == 200
    assert decide(admin_client, reg, "rejected").status_code == 200
    db.refresh(reg)
    assert reg.status == "rejected"
    steps = [(l.from_status, l.to_status) for l in db.scalars(select(StatusLog).order_by(StatusLog.id))]
    assert steps == [("pending", "approved"), ("approved", "kiv"), ("kiv", "rejected")]
    kinds = [e.kind for e in db.scalars(select(EmailLog).where(EmailLog.registration_id == reg.id))]
    assert kinds == ["approved", "kiv", "rejected"]


def test_decision_email_contains_the_note(admin_client, course, db, caplog):
    reg = add_reg(db, course)
    with caplog.at_level("INFO", logger="regsite.mail"):
        decide(admin_client, reg, "kiv", note="Please call me on Monday")
    assert "Please call me on Monday" in caplog.text


def test_decision_without_notify_sends_no_email(admin_client, course, db):
    reg = add_reg(db, course)
    admin_client.post(f"/admin/registrations/{reg.id}/decision", data={"status": "approved"},
                      headers={"HX-Request": "true", "X-CSRF-Token": admin_client.csrf})
    db.refresh(reg)
    assert reg.status == "approved"
    assert db.scalar(select(EmailLog)) is None


def test_row_disappears_when_it_no_longer_matches_the_open_tab(admin_client, course, db):
    reg = add_reg(db, course)
    r = decide(admin_client, reg, "approved", tab="pending")
    assert f'id="row-{reg.id}"' not in r.text
    r = decide(admin_client, reg, "kiv", tab="all")
    assert f'id="row-{reg.id}"' in r.text


def test_approving_past_capacity_warns_but_is_allowed(admin_client, course, db):
    course.capacity = 1
    db.commit()
    a, b = add_reg(db, course, email="a@e.com"), add_reg(db, course, name="B", email="b@e.com")
    decide(admin_client, a, "approved")
    r = decide(admin_client, b, "approved")
    assert "Over capacity" in r.text
    db.refresh(b)
    assert b.status == "approved"


def test_filter_and_search(admin_client, course, db):
    add_reg(db, course, name="Priya S", email="priya@e.com", status="approved", company="Contoso")
    add_reg(db, course, name="Daniel L", email="daniel@e.com", status="pending")
    hx = {"HX-Request": "true", "HX-Target": "table"}
    r = admin_client.get(f"/admin/registrations?course_id={course.id}&status=approved", headers=hx)
    assert "Priya S" in r.text and "Daniel L" not in r.text
    r = admin_client.get(f"/admin/registrations?course_id={course.id}&q=contoso", headers=hx)
    assert "Priya S" in r.text and "Daniel L" not in r.text
    r = admin_client.get(f"/admin/registrations?course_id={course.id}&q=%25", headers=hx)  # a literal %
    assert "Priya S" not in r.text and "No registrations match" in r.text


def test_registrations_page_lists_other_courses_history(admin_client, course, make_course, db):
    old = make_course("Python Basics")
    add_reg(db, old, name="Old Student", email="old@e.com")
    r = admin_client.get(f"/admin/registrations?course_id={old.id}")
    assert "Old Student" in r.text and "Python Basics" in r.text


def test_csv_export_respects_filter_and_neutralises_formulas(admin_client, course, db):
    add_reg(db, course, name="=HYPERLINK(\"http://evil\")", email="evil@e.com", status="approved",
            notes="+cmd|' /C calc'!A0")
    add_reg(db, course, name="Pending Person", email="p@e.com", status="pending")
    r = admin_client.get(f"/admin/registrations.csv?course_id={course.id}&status=approved")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert r.content.startswith(b"\xef\xbb\xbf")  # byte-order mark so Excel reads UTF-8
    body = r.content.decode("utf-8-sig")
    assert "Pending Person" not in body
    assert "'=HYPERLINK" in body and "'+cmd" in body
    assert body.splitlines()[0].startswith("Course,Status,Name,Email,Phone")


def test_resend_email_button(admin_client, course, db):
    reg = add_reg(db, course, status="approved")
    r = admin_client.post(f"/admin/registrations/{reg.id}/resend-email", data={},
                          headers={"HX-Request": "true", "X-CSRF-Token": admin_client.csrf})
    assert r.status_code == 200 and "Email sent." in r.text
    assert db.scalar(select(EmailLog.kind)) == "approved"


def test_unknown_status_is_rejected(admin_client, course, db):
    reg = add_reg(db, course)
    assert decide(admin_client, reg, "banana").status_code == 400


# ---------------------------------------------------------------- courses
def course_form(csrf, **over):
    data = {
        "csrf_token": csrf, "title": "Python Basics", "accent_word": "Python", "tagline": "Start here",
        "introduction": "Para one.\n\nPara two.", "outcomes": ["Write loops", "  ", "Use functions"],
        "prerequisites": ["A laptop"], "audience": ["Beginners"], "module_title": ["Intro", "", "Data"],
        "module_topics": ["Variables\nTypes", "ignored", "Lists\n\nDicts"], "duration_text": "3 days",
        "start_date": "2026-11-12", "end_date": "2026-11-14", "daily_time": "9am - 5pm", "venue": "KL",
        "map_url": "", "fee_text": "RM 1,000", "fee_note": "", "capacity": "25", "registration_deadline": "",
    }
    data.update(over)
    return data


def test_create_course_and_public_page_uses_it(admin_client, course, db):
    r = admin_client.post("/admin/courses/new", data=course_form(admin_client.csrf, is_active="1"),
                          follow_redirects=False)
    assert r.status_code == 303
    new = db.scalar(select(Course).where(Course.title == "Python Basics"))
    assert new.outcomes == ["Write loops", "Use functions"]
    assert new.outline == [{"title": "Intro", "topics": ["Variables", "Types"]},
                           {"title": "Data", "topics": ["Lists", "Dicts"]}]
    db.expire_all()
    assert new.is_active and not db.get(Course, course.id).is_active  # only one is ever active
    home = admin_client.get("/").text
    assert "Python Basics" in home and "12 – 14 November 2026" in home and "RM 1,000" in home


def test_only_one_course_can_be_active(admin_client, course, make_course, db):
    other = make_course("Java")
    admin_client.post(f"/admin/courses/{other.id}/activate", data={"csrf_token": admin_client.csrf})
    db.expire_all()
    assert [c.title for c in db.scalars(select(Course).where(Course.is_active.is_(True)))] == ["Java"]


def test_database_itself_refuses_two_active_courses(db, course, make_course):
    from sqlalchemy.exc import IntegrityError

    other = make_course("Second")
    other.is_active = True
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_duplicate_keeps_history_and_starts_inactive(admin_client, course, db):
    add_reg(db, course)
    r = admin_client.post(f"/admin/courses/{course.id}/duplicate", data={"csrf_token": admin_client.csrf},
                          follow_redirects=False)
    assert r.status_code == 303
    copy = db.scalar(select(Course).where(Course.id != course.id))
    assert copy.title.endswith("(copy)") and not copy.is_active
    assert copy.outcomes == course.outcomes and copy.start_date is None
    assert len(course.registrations) == 1 and not copy.registrations


def test_course_validation_errors(admin_client, course):
    r = admin_client.post("/admin/courses/new", data=course_form(
        admin_client.csrf, title="", capacity="0", start_date="2026-11-14", end_date="2026-11-12"))
    assert r.status_code == 422
    assert "The title is required." in r.text
    assert "Capacity must be a whole number" in r.text
    assert "end date is before the start date" in r.text


def test_cannot_delete_a_course_with_registrations(admin_client, course, db):
    add_reg(db, course)
    admin_client.post(f"/admin/courses/{course.id}/delete", data={"csrf_token": admin_client.csrf})
    assert db.get(Course, course.id) is not None


def test_can_delete_an_empty_course(admin_client, course, make_course, db):
    other_id = make_course("Empty").id
    admin_client.post(f"/admin/courses/{other_id}/delete", data={"csrf_token": admin_client.csrf})
    db.expunge_all()
    assert db.get(Course, other_id) is None


def test_deactivating_makes_public_page_say_nothing_is_open(admin_client, course):
    admin_client.post(f"/admin/courses/{course.id}/deactivate", data={"csrf_token": admin_client.csrf})
    assert "No programme is open" in admin_client.get("/").text


# ---------------------------------------------------------------- site content
def test_site_content_edit_changes_public_page(admin_client, course):
    r = admin_client.post("/admin/site", data={
        "csrf_token": admin_client.csrf, "trainer_name": "Faysal Aziz", "trainer_role": "Trainer",
        "trainer_location": "KL", "trainer_headline": "Hands on.", "trainer_bio": "Bio text.",
        "website_url": "https://faysalaziz.com", "contact_email": "a@b.com",
        "stat_value": ["15,000+", ""], "stat_label": ["Training hours", "ignored"],
        "credentials": ["Certified Trainer"]}, follow_redirects=False)
    assert r.status_code == 303
    home = admin_client.get("/").text
    assert "15,000" in home and "Certified Trainer" in home and "Hands on." in home
    assert "Project implementations" not in home


def test_delete_registration_removes_it_and_keeps_the_email_log(admin_client, course, db):
    reg = add_reg(db, course)
    decide(admin_client, reg, "approved")
    rid = reg.id
    r = admin_client.post(f"/admin/registrations/{rid}/delete", data={"tab": "all"},
                          headers={"HX-Request": "true", "X-CSRF-Token": admin_client.csrf})
    assert r.status_code == 200 and "Registration deleted." in r.text and f'id="row-{rid}"' not in r.text
    db.expunge_all()
    assert db.get(Registration, rid) is None
    assert db.scalar(select(StatusLog)) is None  # decision log goes with it
    assert db.scalar(select(EmailLog.registration_id)) is None  # email record stays, unlinked


def test_api_docs_are_not_exposed(client):
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path).status_code == 404
