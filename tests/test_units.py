from datetime import date
from unittest.mock import patch

import httpx
import pytest
from sqlalchemy import select

from app.config import DEFAULT_SECRET, Settings, assert_safe_for_production
from app.formatting import fmt_date_range, slugify, split_plus
from app.models import EmailLog, Registration
from app.modules.mail import send_student_received
from app.modules.mail.providers import MailError, Message, ResendProvider
from app.security import form_token_age, hash_password, make_form_token, verify_password


def test_date_ranges():
    assert fmt_date_range(None, None) == "To be announced"
    assert fmt_date_range(date(2026, 11, 12), date(2026, 11, 13)) == "12 – 13 November 2026"
    assert fmt_date_range(date(2026, 11, 30), date(2026, 12, 1)) == "30 November – 1 December 2026"
    assert fmt_date_range(date(2026, 12, 30), date(2027, 1, 2)) == "30 December 2026 – 2 January 2027"
    assert fmt_date_range(date(2026, 11, 12), None) == "12 November 2026"


def test_helpers():
    assert slugify("Claude for Builders & Teams!") == "claude-for-builders-teams"
    assert split_plus("10,000+") == ("10,000", "+") and split_plus("32") == ("32", "")


def test_password_hashing():
    h = hash_password("correct horse battery")
    assert h != "correct horse battery" and verify_password(h, "correct horse battery")
    assert not verify_password(h, "wrong") and not verify_password("not-a-hash", "x")


def test_form_token():
    assert form_token_age(make_form_token()) == 0
    assert form_token_age("forged") is None and form_token_age("") is None


def test_production_refuses_unsafe_settings():
    with pytest.raises(RuntimeError) as exc:
        assert_safe_for_production(Settings(app_env="production", secret_key=DEFAULT_SECRET,
                                                base_url="http://example.com", _env_file=None))
    assert "SECRET_KEY" in str(exc.value) and "https://" in str(exc.value)
    good = Settings(app_env="production", secret_key="x" * 40, base_url="https://example.com",
                    mail_provider="resend", resend_api_key="re_123", _env_file=None)
    assert_safe_for_production(good)


def _resp(status, payload):
    return httpx.Response(status, json=payload, request=httpx.Request("POST", ResendProvider.url))


MSG = Message(to="a@b.com", subject="Hi", html="<p>Hi</p>", text="Hi", from_addr="Me <me@x.com>",
              reply_to="r@x.com", idempotency_key="k1")


def test_resend_provider_request_shape():
    with patch("httpx.post", return_value=_resp(200, {"id": "abc"})) as post:
        assert ResendProvider("re_key").send(MSG) == "abc"
    kwargs = post.call_args.kwargs
    assert kwargs["json"] == {"from": "Me <me@x.com>", "to": ["a@b.com"], "subject": "Hi",
                              "html": "<p>Hi</p>", "text": "Hi", "reply_to": "r@x.com"}
    assert kwargs["headers"]["Authorization"] == "Bearer re_key"
    assert kwargs["headers"]["Idempotency-Key"] == "k1"


def test_resend_client_errors_are_not_retried():
    with patch("httpx.post", return_value=_resp(403, {"message": "domain not verified"})) as post:
        with pytest.raises(MailError, match="403.*domain not verified"):
            ResendProvider("k").send(MSG)
    assert post.call_count == 1


def test_resend_retries_server_errors_once():
    with patch("httpx.post", side_effect=[_resp(500, {"message": "boom"}), _resp(200, {"id": "ok"})]), \
            patch("time.sleep"):
        assert ResendProvider("k").send(MSG) == "ok"


def test_failed_email_is_logged_and_never_raises(course, db, monkeypatch):
    monkeypatch.setenv("MAIL_PROVIDER", "resend")
    monkeypatch.setenv("RESEND_API_KEY", "re_key")
    from app.config import get_settings

    get_settings.cache_clear()
    reg = Registration(course_id=course.id, name="A B", email="a@b.com", email_key="a@b.com",
                       phone="0123456789", consent=True)
    db.add(reg)
    db.commit()
    try:
        with patch("httpx.post", return_value=_resp(403, {"message": "domain not verified"})):
            assert send_student_received(reg.id) is False
        entry = db.scalar(select(EmailLog))
        assert entry.status == "failed" and "domain not verified" in entry.error
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()
