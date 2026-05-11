"""Telegram message renderers for bot menu screens.

Pure functions: take primitive data (already loaded from DB), return an
HTML-formatted string for Telegram (parse_mode=HTML). User-supplied content
(market titles, explanations) is HTML-escaped — Markdown was retired because
real-world Polymarket titles contain underscores/asterisks that broke the
legacy Markdown parser mid-message.
"""
from __future__ import annotations

import html
from dataclasses import dataclass
from datetime import datetime, timezone

from app.schemas.api import StatsOut


_TITLE_LIMIT = 50


def _trim(title: str, limit: int = _TITLE_LIMIT) -> str:
    title = (title or "").strip()
    if len(title) <= limit:
        return title
    return title[: limit - 1].rstrip() + "…"


def _h(text: str) -> str:
    """HTML-escape user-sourced text. Safe to call on already-trimmed strings."""
    return html.escape(text or "", quote=False)


def _signed_pct(value: float) -> str:
    pct = value * 100
    if abs(pct) < 0.05:
        return "0.0%"
    sign = "+" if pct > 0 else ""
    return f"{sign}{pct:.1f}%"


def _signed_money(value: float) -> str:
    if abs(value) < 0.005:
        return "$0.00"
    sign = "+" if value > 0 else ""
    return f"{sign}${value:.2f}"


def _status_emoji(status: str) -> str:
    mapping = {
        "paper_trade_candidate": "🟢",
        "valid_signal": "🟡",
        "weak_signal": "⚪️",
        "informational": "ℹ️",
        "suppressed_by_risk": "🛑",
        "blocked_by_antipattern": "🚫",
        "ignored_manually": "🙈",
    }
    return mapping.get(status, "•")


def _direction_emoji(direction: str) -> str:
    return "📈" if (direction or "").upper() == "YES" else "📉"


def render_main_menu_title() -> str:
    return "Главное меню\n\nВыберите раздел ниже."


def render_stats(stats: StatsOut) -> str:
    delta = stats.equity - stats.initial_balance
    delta_pct = (delta / stats.initial_balance) if stats.initial_balance else 0.0
    delta_emoji = "🚀" if delta > 0 else ("📉" if delta < 0 else "➖")

    version_suffix = (
        f" · стратегия v{stats.active_strategy_version}"
        if stats.active_strategy_version is not None
        else ""
    )

    lines = [
        f"📊 <b>Сводка псевдоторговли</b>{version_suffix}",
        "",
        f"💰 Equity: <b>${stats.equity:.2f}</b> (старт ${stats.initial_balance:.2f})",
        f"{delta_emoji} Изменение: {_signed_money(delta)} ({_signed_pct(delta_pct)})",
        f"   Cash ${stats.balance:.2f} · Locked ${stats.locked_in_open:.2f} в {stats.open_paper_trades} откр.",
        "",
        "💼 Сделки активной стратегии",
        f"   ⏳ Открытые: {stats.open_paper_trades}",
        f"   ✅ Закрытые: {stats.closed_paper_trades}",
        f"   🎯 Winrate: {stats.winrate * 100:.0f}%",
        "",
        "📈 P&amp;L закрытых",
        f"   Σ итого: {_signed_money(stats.total_pnl)}",
        f"   ⌀ средний: {_signed_money(stats.avg_pnl)}",
        f"   ✨ лучший: {_signed_money(stats.best_pnl)}",
        f"   💀 худший: {_signed_money(stats.worst_pnl)}",
        "",
        f"📡 Активных сигналов: {stats.active_signals_count}",
    ]

    if stats.past_strategies:
        lines.append("")
        lines.append("📜 Прошлые стратегии")
        for past in stats.past_strategies:
            lines.append(
                f"   v{past.version}: {past.closed_trades} закр. · {_signed_money(past.total_pnl)}"
            )

    return "\n".join(lines)


@dataclass
class TradeRow:
    market_title: str
    direction: str
    entry: float
    current: float
    status: str
    realized_pnl: float | None
    close_reason: str | None
    open_time: datetime


def render_trades(trades: list[TradeRow]) -> str:
    if not trades:
        return "💼 <b>Сделки</b>\n\nПока нет ни одной открытой или закрытой сделки.\nКак только бот найдёт подходящий сигнал — он откроет позицию автоматически."

    lines = ["💼 <b>Сделки</b>\n"]
    for t in trades:
        title = _h(_trim(t.market_title))
        head = f"{_direction_emoji(t.direction)} {title}"
        if t.status == "open":
            move_pct = (t.current - t.entry) / t.entry if t.entry else 0.0
            if t.direction.upper() == "NO":
                move_pct = -move_pct
            mark = "🟢" if move_pct >= 0 else "🔴"
            sub = (
                f"   ⏳ открыта · вход {t.entry:.2f} → сейчас {t.current:.2f} · "
                f"{mark} {_signed_pct(move_pct)}"
            )
        else:
            pnl = t.realized_pnl or 0.0
            move_emoji = "✅" if pnl > 0 else ("❌" if pnl < 0 else "➖")
            reason = {
                "take_profit": "тейк",
                "stop_loss": "стоп",
                "time_limit": "время",
                "market_inactive": "рынок закрыт",
                "strategy_migration": "миграция стратегии",
            }.get(t.close_reason or "", _h(t.close_reason or ""))
            sub = (
                f"   {move_emoji} закрыта · вход {t.entry:.2f} → выход {t.current:.2f} · "
                f"{_signed_money(pnl)} · ({reason})"
            )
        lines.append(head)
        lines.append(sub)
        lines.append("")
    return "\n".join(lines).rstrip()


@dataclass
class SignalRow:
    market_title: str
    status: str
    edge: float
    confidence: float
    explanation: str | None
    created_at: datetime


def render_signals(signals: list[SignalRow]) -> str:
    if not signals:
        return "📡 <b>Сигналы</b>\n\nПока нет ни одного сигнала. Бот всё ещё анализирует свежие новости."

    lines = ["📡 <b>Свежие сигналы</b>\n"]
    for s in signals:
        title = _h(_trim(s.market_title))
        direction = "📈 в YES" if s.edge >= 0 else "📉 в NO"
        edge_str = _signed_pct(s.edge)
        conf_str = f"{s.confidence * 100:.0f}%"
        head = f"{_status_emoji(s.status)} {title}"
        sub = f"   {direction} · edge {edge_str} · уверенность {conf_str}"
        lines.append(head)
        lines.append(sub)
        if s.explanation:
            lines.append(f"   💬 {_h(_trim(s.explanation, 100))}")
        lines.append("")
    return "\n".join(lines).rstrip()


@dataclass
class MarketRow:
    title: str
    yes_price: float | None
    liquidity: float | None
    captured_at: datetime | None


def render_markets(markets: list[MarketRow]) -> str:
    if not markets:
        return "🎯 <b>Рынки</b>\n\nСписок рынков пуст. Бот синхронизируется с Polymarket в фоне."

    lines = ["🎯 <b>Топ рынков под наблюдением</b>\n"]
    for m in markets:
        title = _h(_trim(m.title))
        if m.yes_price is None:
            price_part = "цена не получена"
        else:
            price_part = f"YES {m.yes_price * 100:.0f}%"
        if m.liquidity:
            price_part += f" · ликв. ${m.liquidity:,.0f}"
        lines.append(f"• {title}")
        lines.append(f"   {price_part}")
        lines.append("")
    return "\n".join(lines).rstrip()


def now_utc() -> datetime:
    return datetime.now(timezone.utc)
