import pytest

from app.core.config import Settings
from app.services.auth_service import AccessDeniedError, AuthService


def test_auth_service_allows_allowed_user() -> None:
    settings = Settings(_env_file=None, TELEGRAM_ALLOWED_USER_IDS="111,222")
    service = AuthService(settings=settings)
    service.ensure_allowed(111)


def test_auth_service_denies_not_allowed_user() -> None:
    settings = Settings(_env_file=None, TELEGRAM_ALLOWED_USER_IDS="111,222")
    service = AuthService(settings=settings)
    with pytest.raises(AccessDeniedError):
        service.ensure_allowed(333)


def test_auth_service_allows_all_when_allowlist_is_empty() -> None:
    settings = Settings(_env_file=None, TELEGRAM_ALLOWED_USER_IDS="")
    service = AuthService(settings=settings)
    service.ensure_allowed(999)

