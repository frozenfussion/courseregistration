"""Send one test email with the configured provider:  python -m scripts.send_test_email you@example.com

Use it after setting RESEND_API_KEY to prove the sender, domain and key all work. It prints the provider's
answer and never prints the API key.
"""
import sys

from app.config import get_settings
from app.modules.mail.providers import MailError, Message, get_provider


def main() -> int:
    if len(sys.argv) != 2 or "@" not in sys.argv[1]:
        print("Usage: python -m scripts.send_test_email you@example.com")
        return 2
    s = get_settings()
    try:
        provider = get_provider(s)
        message_id = provider.send(Message(
            to=sys.argv[1],
            subject="Test email from the registration site",
            html="<p>If you can read this, email sending works.</p>",
            text="If you can read this, email sending works.",
            from_addr=s.mail_from,
            reply_to=s.mail_reply_to,
        ))
    except MailError as exc:
        print(f"FAILED ({s.mail_provider}): {exc}")
        return 1
    print(f"Sent with {provider.name} from {s.mail_from}. Provider id: {message_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
