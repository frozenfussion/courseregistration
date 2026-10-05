from datetime import date, timedelta

from sqlalchemy import select

from app.models import APPROVED, EmailLog, Registration
from tests.conftest import registration_form


def test_home_without_active_course(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "No programme is open for registration" in r.text
    assert "Submit registration" not in r.text


def test_home_shows_active_course(client, course):
    r = client.get("/")
    assert r.status_code == 200
    assert "Claude for" in r.text and "Builders" in r.text
    assert "To be announced" in r.text  # dates, venue and fee are not set yet
    assert "29 of 30 seats left" not in r.text and "30 of 30 seats left" in r.text
    assert 'id="register-card"' in r.text
    assert "10,000" in r.text  # trainer highlights


def test_security_headers(client):
    r = client.get("/")
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["x-content-type-options"] == "nosniff"
    assert "frame-ancestors 'none'" in r.headers["content-security-policy"]


def test_register_saves_and_sends_emails(client, course, db):
    r = client.post("/register", data=registration_form(), headers={"HX-Request": "true"})
    assert r.status_code == 200
    assert "Request received" in r.text
    assert "<html" not in r.text  # htmx gets only the card

    reg = db.scalar(select(Registration))
    assert reg.name == "Aisyah Rahman" and reg.status == "pending" and reg.consent
    kinds = {(e.kind, e.to_email, e.status) for e in db.scalars(select(EmailLog))}
    assert ("received", "aisyah@example.com", "sent") in kinds
    assert ("admin_alert", "faysalabdulaziz@gmail.com", "sent") in kinds


def test_register_without_javascript_returns_full_page(client, course):
    r = client.post("/register", data=registration_form())
    assert r.status_code == 200
    assert "<html" in r.text and "Request received" in r.text


def test_validation_errors_keep_the_values(client, course, db):
    r = client.post("/register", data=registration_form(email="nope", phone="12", consent=""),
                    headers={"HX-Request": "true"})
    assert "Please enter a valid email address." in r.text
    assert "Please enter a valid phone number." in r.text
    assert "Please tick the box to continue." in r.text
    assert 'value="Aisyah Rahman"' in r.text
    assert db.scalar(select(Registration)) is None


def test_duplicate_email_is_refused_case_insensitively(client, course, db):
    client.post("/register", data=registration_form())
    r = client.post("/register", data=registration_form(email="AISYAH@Example.com"),
                    headers={"HX-Request": "true"})
    assert "already registered" in r.text
    assert len(list(db.scalars(select(Registration)))) == 1


def test_honeypot_looks_like_success_but_saves_nothing(client, course, db):
    r = client.post("/register", data=registration_form(website="http://spam.example"),
                    headers={"HX-Request": "true"})
    assert "Request received" in r.text
    assert db.scalar(select(Registration)) is None


def test_missing_form_token_is_treated_as_a_bot(client, course, db):
    r = client.post("/register", data=registration_form(ft="forged"), headers={"HX-Request": "true"})
    assert "Request received" in r.text
    assert db.scalar(select(Registration)) is None


def test_rate_limit_per_network(client, course, db):
    for i in range(5):
        client.post("/register", data=registration_form(email=f"p{i}@example.com"))
    r = client.post("/register", data=registration_form(email="p9@example.com"), headers={"HX-Request": "true"})
    assert "Too many registrations" in r.text
    assert len(list(db.scalars(select(Registration)))) == 5


def test_many_links_are_flagged_not_blocked(client, course, db):
    client.post("/register", data=registration_form(notes="see http://a.example and http://b.example"))
    reg = db.scalar(select(Registration))
    assert reg.flagged and "links" in reg.flag_reason


def test_full_course_closes_registration(client, course, db):
    course.capacity = 1
    db.add(Registration(course_id=course.id, name="X Y", email="x@example.com", email_key="x@example.com",
                        phone="0123456789", status=APPROVED, consent=True))
    db.commit()
    assert "Fully booked" in client.get("/").text
    r = client.post("/register", data=registration_form(), headers={"HX-Request": "true"})
    assert "fully booked" in r.text.lower()
    assert len(list(db.scalars(select(Registration)))) == 1


def test_pending_and_kiv_do_not_use_seats(client, course, db):
    course.capacity = 1
    for i, status in enumerate(("pending", "kiv", "rejected")):
        db.add(Registration(course_id=course.id, name="N N", email=f"{i}@e.com", email_key=f"{i}@e.com",
                            phone="0123456789", status=status, consent=True))
    db.commit()
    assert "1 of 1 seats left" in client.get("/").text


def test_deadline_closes_registration(client, course, db):
    course.registration_deadline = date.today() - timedelta(days=1)
    db.commit()
    page = client.get("/")
    assert "Registration closed" in page.text
    r = client.post("/register", data=registration_form(), headers={"HX-Request": "true"})
    assert "deadline has passed" in r.text


def test_brochure_pdf_is_built_from_the_course(client, course):
    r = client.get("/brochure.pdf")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content.startswith(b"%PDF")
    assert "claude-for-builders-and-technical-teams-brochure.pdf" in r.headers["content-disposition"]


def test_brochure_404_without_active_course(client):
    assert client.get("/brochure.pdf").status_code == 404


def test_404_page_is_friendly(client):
    r = client.get("/nope", headers={"Accept": "text/html"})
    assert r.status_code == 404 and "This page does not exist" in r.text


def test_healthz(client):
    assert client.get("/healthz").json() == {"status": "ok"}


def test_text_email_is_not_html_escaped_and_newlines_in_names_are_neutralised(client, course, db, caplog):
    with caplog.at_level("INFO", logger="regsite.mail"):
        client.post("/register", data=registration_form(name="Siti O'Brien\r\nBcc: evil@example.com & Co",
                                                        email="siti@example.com"))
    reg = db.scalar(select(Registration))
    assert "\n" not in reg.name and "\r" not in reg.name
    assert "O'Brien" in caplog.text and "&#39;" not in caplog.text
