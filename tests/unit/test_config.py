from app.core.config import Settings


def test_settings_parses_telegram_allowed_user_ids() -> None:
    settings = Settings(_env_file=None, TELEGRAM_ALLOWED_USER_IDS="123, 456,789")
    assert settings.telegram_allowed_user_ids == [123, 456, 789]


def test_settings_empty_telegram_allowed_user_ids() -> None:
    settings = Settings(_env_file=None, TELEGRAM_ALLOWED_USER_IDS="")
    assert settings.telegram_allowed_user_ids == []

