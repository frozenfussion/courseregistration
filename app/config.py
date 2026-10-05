"""Application settings, read from environment variables and an optional .env file."""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_SECRET = "dev-only-insecure-secret-change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    # Core
    app_env: str = "development"  # "production" turns on secure cookies and safety checks
    secret_key: str = DEFAULT_SECRET
    base_url: str = "http://127.0.0.1:8000"
    database_url: str = f"sqlite:///{BASE_DIR / 'data' / 'regsite.db'}"
    timezone: str = "Asia/Kuala_Lumpur"

    # Mail: provider is "resend", "smtp" or "console" (console only logs, for development)
    mail_provider: str = "console"
    mail_from: str = "Faysal Aziz <registration@register.faysalaziz.com>"
    mail_reply_to: str = "faysalabdulaziz@gmail.com"
    admin_alert_email: str = "faysalabdulaziz@gmail.com"
    resend_api_key: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_starttls: bool = True

    # Abuse protection
    registration_rate_limit: int = 5  # registrations per network address per hour
    min_form_seconds: int = 3  # a human needs a few seconds to fill the form
    login_max_attempts: int = 5  # failed logins per address per window
    login_window_minutes: int = 15
    session_hours: int = 12

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()


def assert_safe_for_production(settings: Settings) -> None:
    """Refuse to start in production with unsafe defaults."""
    if not settings.is_production:
        return
    problems = []
    if settings.secret_key == DEFAULT_SECRET or len(settings.secret_key) < 32:
        problems.append("SECRET_KEY must be a random string of at least 32 characters")
    if not settings.base_url.startswith("https://"):
        problems.append("BASE_URL must start with https:// in production")
    if settings.mail_provider == "resend" and not settings.resend_api_key:
        problems.append("RESEND_API_KEY is required when MAIL_PROVIDER=resend")
    if settings.mail_provider == "smtp" and not settings.smtp_host:
        problems.append("SMTP_HOST is required when MAIL_PROVIDER=smtp")
    if problems:
        raise RuntimeError("Unsafe production configuration:\n- " + "\n- ".join(problems))
