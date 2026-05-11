import asyncio
import structlog

from aiogram import Bot, Dispatcher
from aiogram.exceptions import TelegramAPIError

from app.bot.handlers.menu import router
from app.core.config import get_settings
from app.core.logging import configure_logging

logger = structlog.get_logger(__name__)


async def run_bot() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is required")

    bot = Bot(token=settings.telegram_bot_token)
    dispatcher = Dispatcher()
    dispatcher.include_router(router)

    try:
        me = await bot.get_me()
        logger.info(
            "bot_startup",
            bot_id=me.id,
            bot_username=me.username,
            allowed_user_ids=settings.telegram_allowed_user_ids,
        )
        await bot.delete_webhook(drop_pending_updates=False)
        logger.info("webhook_disabled_for_polling")
        await dispatcher.start_polling(bot)
    except TelegramAPIError as exc:
        logger.error("telegram_api_error", error=str(exc))
        raise
    finally:
        await bot.session.close()


def main() -> None:
    asyncio.run(run_bot())


if __name__ == "__main__":
    main()
