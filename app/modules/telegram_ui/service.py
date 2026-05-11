from aiogram.types import InlineKeyboardMarkup

from app.bot.keyboards import main_menu_keyboard


class TelegramUIModule:
    def build_main_menu(self) -> InlineKeyboardMarkup:
        return main_menu_keyboard()
