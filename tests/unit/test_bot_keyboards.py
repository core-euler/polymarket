from app.bot.keyboards import back_main_keyboard, main_menu_keyboard


def _collect_callback_data(markup) -> list[str]:
    return [
        button.callback_data
        for row in markup.inline_keyboard
        for button in row
        if button.callback_data
    ]


def test_main_menu_keyboard_contains_only_working_sections() -> None:
    callbacks = _collect_callback_data(main_menu_keyboard())
    assert callbacks == [
        "menu:statistics",
        "menu:paper_trades",
        "menu:signals",
        "menu:markets",
        "menu:force_refresh",
    ]


def test_main_menu_keyboard_drops_placeholder_sections() -> None:
    callbacks = _collect_callback_data(main_menu_keyboard())
    assert "menu:error_reviews" not in callbacks
    assert "menu:antipatterns" not in callbacks
    assert "menu:settings" not in callbacks


def test_back_main_keyboard_has_back_button() -> None:
    callbacks = _collect_callback_data(back_main_keyboard())
    assert callbacks == ["menu:main"]
