import pytest
from pydantic import ValidationError

from app.config import Settings


def _production_settings(**overrides) -> Settings:
    values = {
        "environment": "production",
        "database_url": "postgresql+asyncpg://markliv:test@localhost:5432/mark_liv",
        "jwt_secret": "test-secret-not-for-production-0123456789abcdef",
        "cors_origins": "https://app.example.com",
        "email_backend": "smtp",
        "smtp_host": "smtp.example.com",
        "smtp_from": "no-reply@example.com",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_production_settings_accept_persistent_secure_configuration():
    settings = _production_settings()

    assert settings.is_production
    assert settings.database_url.startswith("postgresql+asyncpg://")


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"jwt_secret": ""}, "JWT_SECRET"),
        ({"jwt_secret": "short"}, "JWT_SECRET"),
        ({"database_url": "sqlite+aiosqlite:///./mark_liv_dev.db"}, "DATABASE_URL"),
        ({"cors_origins": "*"}, "CORS_ORIGINS"),
        ({"email_backend": "console"}, "EMAIL_BACKEND"),
        ({"smtp_host": ""}, "SMTP_HOST"),
        ({"smtp_from": "no-reply@mark-liv.local"}, "SMTP_FROM"),
        ({"smtp_username": "markliv"}, "SMTP_USERNAME and SMTP_PASSWORD"),
    ],
)
def test_production_settings_reject_unsafe_or_incomplete_configuration(
    override, message
):
    with pytest.raises(ValidationError, match=message):
        _production_settings(**override)
