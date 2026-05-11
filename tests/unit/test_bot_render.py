from datetime import datetime, timezone

from app.bot.render import (
    MarketRow,
    SignalRow,
    TradeRow,
    render_markets,
    render_signals,
    render_stats,
    render_trades,
)
from app.schemas.api import StatsOut


def _ts() -> datetime:
    return datetime(2026, 5, 7, 12, 0, tzinfo=timezone.utc)


def test_render_stats_shows_balance_delta_and_pnl_block() -> None:
    text = render_stats(
        StatsOut(
            active_strategy_version=2,
            total_signals=4,
            total_paper_trades=3,
            open_paper_trades=2,
            closed_paper_trades=1,
            winrate=1.0,
            balance=99.50,
            locked_in_open=2.00,
            equity=101.50,
            initial_balance=100.0,
            total_pnl=1.5,
            avg_pnl=1.5,
            best_pnl=1.5,
            worst_pnl=1.5,
            active_signals_count=4,
        )
    )
    assert "Сводка псевдоторговли" in text
    assert "стратегия v2" in text
    assert "Equity:" in text
    assert "$101.50" in text
    assert "+$1.50" in text
    assert "Winrate: 100%" in text
    assert "Открытые: 2" in text
    assert "Закрытые: 1" in text
    assert "Cash $99.50" in text
    assert "Locked $2.00" in text
    assert "Активных сигналов: 4" in text


def test_render_trades_open_includes_unrealized_move() -> None:
    rows = [
        TradeRow(
            market_title="Will candidate Smith win the election?",
            direction="YES",
            entry=0.40,
            current=0.50,
            status="open",
            realized_pnl=None,
            close_reason=None,
            open_time=_ts(),
        )
    ]
    text = render_trades(rows)
    assert "📈" in text
    assert "вход 0.40" in text
    assert "сейчас 0.50" in text
    assert "+25.0%" in text


def test_render_trades_closed_shows_pnl_and_reason() -> None:
    rows = [
        TradeRow(
            market_title="Iran peace deal",
            direction="NO",
            entry=0.50,
            current=0.45,
            status="closed",
            realized_pnl=0.5,
            close_reason="take_profit",
            open_time=_ts(),
        )
    ]
    text = render_trades(rows)
    assert "📉" in text
    assert "+$0.50" in text
    assert "тейк" in text


def test_render_signals_handles_negative_edge() -> None:
    rows = [
        SignalRow(
            market_title="Market X",
            status="paper_trade_candidate",
            edge=-0.12,
            confidence=0.7,
            explanation="Reason here.",
            created_at=_ts(),
        )
    ]
    text = render_signals(rows)
    assert "🟢" in text
    assert "📉 в NO" in text
    assert "edge -12.0%" in text
    assert "уверенность 70%" in text
    assert "Reason here." in text


def test_render_signals_empty_state() -> None:
    text = render_signals([])
    assert "анализирует" in text


def test_render_markets_with_price() -> None:
    rows = [
        MarketRow(
            title="Will Bitcoin hit $200k?",
            yes_price=0.42,
            liquidity=12345.6,
            captured_at=_ts(),
        )
    ]
    text = render_markets(rows)
    assert "Will Bitcoin hit $200k?" in text
    assert "YES 42%" in text
    assert "ликв." in text


def test_render_trades_empty_state_friendly() -> None:
    text = render_trades([])
    assert "Пока нет ни одной открытой" in text


def test_render_trades_no_negative_zero_glitch() -> None:
    rows = [
        TradeRow(
            market_title="Flat market",
            direction="YES",
            entry=0.10,
            current=0.10,
            status="open",
            realized_pnl=None,
            close_reason=None,
            open_time=_ts(),
        )
    ]
    text = render_trades(rows)
    assert "+-" not in text
    assert "0.0%" in text


def test_render_stats_zero_delta_clean() -> None:
    text = render_stats(
        StatsOut(
            active_strategy_version=2,
            total_signals=0,
            total_paper_trades=0,
            open_paper_trades=0,
            closed_paper_trades=0,
            winrate=0.0,
            balance=100.0,
            locked_in_open=0.0,
            equity=100.0,
            initial_balance=100.0,
            total_pnl=0.0,
            avg_pnl=0.0,
            best_pnl=0.0,
            worst_pnl=0.0,
            active_signals_count=0,
        )
    )
    assert "+-" not in text
    assert "$0.00" in text


def test_render_stats_includes_past_strategies_block_when_present() -> None:
    from app.schemas.api import PastStrategySummary

    text = render_stats(
        StatsOut(
            active_strategy_version=2,
            total_signals=10,
            total_paper_trades=5,
            open_paper_trades=2,
            closed_paper_trades=3,
            winrate=0.33,
            balance=99.7,
            locked_in_open=0.2,
            equity=99.9,
            initial_balance=100.0,
            total_pnl=-0.1,
            avg_pnl=-0.03,
            best_pnl=0.0,
            worst_pnl=-0.1,
            active_signals_count=8,
            past_strategies=[
                PastStrategySummary(version=1, closed_trades=18, total_pnl=0.09),
            ],
        )
    )
    assert "Прошлые стратегии" in text
    assert "v1: 18 закр." in text
    assert "+$0.09" in text
