from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def main_menu_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📊 Статистика", callback_data="menu:statistics")
    builder.button(text="💼 Сделки", callback_data="menu:paper_trades")
    builder.button(text="📡 Сигналы", callback_data="menu:signals")
    builder.button(text="🎯 Рынки", callback_data="menu:markets")
    builder.button(text="🔄 Force refresh", callback_data="menu:force_refresh")
    builder.adjust(2, 2, 1)
    return builder.as_markup()


def back_main_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="◀️ Назад", callback_data="menu:main")
    return builder.as_markup()
