from __future__ import annotations

import httpx
import structlog
from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards import back_main_keyboard, main_menu_keyboard
from app.bot.render import (
    MarketRow,
    SignalRow,
    TradeRow,
    render_main_menu_title,
    render_markets,
    render_signals,
    render_stats,
    render_trades,
)
from app.db.models import Market, MarketSnapshot, PaperTrade, Signal
from app.db.session import SessionLocal
from app.services.container import build_container

router = Router()
container = build_container()
logger = structlog.get_logger(__name__)


async def _ensure_access(user_id: int) -> bool:
    try:
        container.auth_service.ensure_allowed(user_id)
        return True
    except Exception:
        return False


async def _send_screen(callback: CallbackQuery, text: str) -> None:
    if callback.message:
        await callback.message.edit_text(
            text, reply_markup=back_main_keyboard(), parse_mode="HTML"
        )
    await callback.answer()


@router.message(CommandStart())
async def start_handler(message: Message) -> None:
    user_id = message.from_user.id if message.from_user else None
    logger.info("telegram_start_received", user_id=user_id)
    if not message.from_user or not await _ensure_access(message.from_user.id):
        denied_user = str(user_id) if user_id is not None else "unknown"
        await message.answer(f"Access denied. Your user id: {denied_user}")
        return
    await message.answer(render_main_menu_title(), reply_markup=main_menu_keyboard())


@router.callback_query(F.data == "menu:main")
async def main_menu_handler(callback: CallbackQuery) -> None:
    if not callback.from_user or not await _ensure_access(callback.from_user.id):
        await callback.answer("Access denied.", show_alert=True)
        return
    if callback.message:
        await callback.message.edit_text(
            render_main_menu_title(), reply_markup=main_menu_keyboard()
        )
    await callback.answer()


@router.callback_query(F.data == "menu:statistics")
async def stats_handler(callback: CallbackQuery) -> None:
    if not callback.from_user or not await _ensure_access(callback.from_user.id):
        await callback.answer("Access denied.", show_alert=True)
        return
    async with SessionLocal() as session:
        stats = await container.analytics_service.get_stats(session=session)
    await _send_screen(callback, render_stats(stats))


@router.callback_query(F.data == "menu:paper_trades")
async def paper_trades_handler(callback: CallbackQuery) -> None:
    if not callback.from_user or not await _ensure_access(callback.from_user.id):
        await callback.answer("Access denied.", show_alert=True)
        return
    async with SessionLocal() as session:
        rows = await _load_trade_rows(session, limit=10)
    await _send_screen(callback, render_trades(rows))


@router.callback_query(F.data == "menu:signals")
async def signals_handler(callback: CallbackQuery) -> None:
    if not callback.from_user or not await _ensure_access(callback.from_user.id):
        await callback.answer("Access denied.", show_alert=True)
        return
    async with SessionLocal() as session:
        rows = await _load_signal_rows(session, limit=8)
    await _send_screen(callback, render_signals(rows))


@router.callback_query(F.data == "menu:markets")
async def markets_handler(callback: CallbackQuery) -> None:
    if not callback.from_user or not await _ensure_access(callback.from_user.id):
        await callback.answer("Access denied.", show_alert=True)
        return
    async with SessionLocal() as session:
        rows = await _load_market_rows(session, limit=10)
    await _send_screen(callback, render_markets(rows))


@router.callback_query(F.data == "menu:force_refresh")
async def force_refresh_handler(callback: CallbackQuery) -> None:
    if not callback.from_user or not await _ensure_access(callback.from_user.id):
        await callback.answer("Access denied.", show_alert=True)
        return

    base_url = container.settings.internal_api_base_url.rstrip("/")
    url = f"{base_url}/api/v1/admin/run-pipeline"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url)
            response.raise_for_status()
            payload = response.json()
    except Exception as exc:
        logger.warning("force_refresh_failed", error=str(exc))
        await callback.answer("Не удалось запустить пайплайн", show_alert=True)
        return

    chain_id = payload.get("chain_id") or "—"
    text = (
        "🔄 <b>Force refresh</b>\n\n"
        "Пайплайн поставлен в очередь:\n"
        "<code>news_ingest → analysis → signals → paper_trades</code>\n\n"
        f"Chain id: <code>{chain_id}</code>\n\n"
        "Через минуту-две обнови экраны Сигналы / Сделки."
    )
    await _send_screen(callback, text)


async def _load_trade_rows(session: AsyncSession, *, limit: int) -> list[TradeRow]:
    stmt = (
        select(PaperTrade, Market.title)
        .join(Market, Market.id == PaperTrade.market_id)
        .order_by(PaperTrade.id.desc())
        .limit(limit)
    )
    result = (await session.execute(stmt)).all()
    rows: list[TradeRow] = []
    for trade, market_title in result:
        if trade.status == "open":
            current = await _latest_yes_price(session, market_id=trade.market_id)
            current_price = current if current is not None else trade.entry_price
        else:
            current_price = trade.exit_price if trade.exit_price is not None else trade.entry_price
        rows.append(
            TradeRow(
                market_title=market_title or "",
                direction=trade.direction or "",
                entry=float(trade.entry_price or 0.0),
                current=float(current_price or 0.0),
                status=trade.status or "",
                realized_pnl=float(trade.realized_pnl) if trade.realized_pnl is not None else None,
                close_reason=trade.close_reason,
                open_time=trade.open_time,
            )
        )
    return rows


async def _load_signal_rows(session: AsyncSession, *, limit: int) -> list[SignalRow]:
    stmt = (
        select(Signal, Market.title)
        .join(Market, Market.id == Signal.market_id)
        .order_by(Signal.id.desc())
        .limit(limit)
    )
    result = (await session.execute(stmt)).all()
    return [
        SignalRow(
            market_title=market_title or "",
            status=signal.status or "",
            edge=float(signal.edge or 0.0),
            confidence=float(signal.confidence or 0.0),
            explanation=signal.explanation,
            created_at=signal.created_at,
        )
        for signal, market_title in result
    ]


async def _load_market_rows(session: AsyncSession, *, limit: int) -> list[MarketRow]:
    stmt = (
        select(Market)
        .where(Market.status == "active", Market.archived_flag.is_(False))
        .order_by(Market.id.desc())
        .limit(limit)
    )
    markets = list(await session.scalars(stmt))
    rows: list[MarketRow] = []
    for market in markets:
        snapshot = await session.scalar(
            select(MarketSnapshot)
            .where(MarketSnapshot.market_id == market.id)
            .order_by(MarketSnapshot.captured_at.desc(), MarketSnapshot.id.desc())
        )
        rows.append(
            MarketRow(
                title=market.title or market.question or "",
                yes_price=(
                    float(snapshot.implied_probability or snapshot.last_price)
                    if snapshot
                    else None
                ),
                liquidity=float(snapshot.liquidity) if snapshot and snapshot.liquidity else None,
                captured_at=snapshot.captured_at if snapshot else None,
            )
        )
    return rows


async def _latest_yes_price(session: AsyncSession, *, market_id: int) -> float | None:
    snapshot = await session.scalar(
        select(MarketSnapshot)
        .where(MarketSnapshot.market_id == market_id)
        .order_by(MarketSnapshot.captured_at.desc(), MarketSnapshot.id.desc())
    )
    if snapshot is None:
        return None
    return float(snapshot.implied_probability or snapshot.last_price or 0.0)
