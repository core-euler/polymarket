from app.modules.telegram_ui.service import TelegramUIModule


def test_telegram_ui_module_builds_main_menu() -> None:
    module = TelegramUIModule()
    markup = module.build_main_menu()
    callbacks = [
        button.callback_data
        for row in markup.inline_keyboard
        for button in row
        if button.callback_data
    ]
    assert callbacks == [
        "menu:statistics",
        "menu:paper_trades",
        "menu:signals",
        "menu:markets",
        "menu:force_refresh",
    ]

