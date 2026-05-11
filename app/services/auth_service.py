from app.core.config import Settings


class AccessDeniedError(Exception):
    pass


class AuthService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def ensure_allowed(self, telegram_user_id: int) -> None:
        allowed = self.settings.telegram_allowed_user_ids
        if not allowed:
            return
        if telegram_user_id not in allowed:
            raise AccessDeniedError(f"User {telegram_user_id} is not allowed")

