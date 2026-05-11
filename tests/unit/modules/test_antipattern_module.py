from datetime import datetime, timezone

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.models import (
    Antipattern,
    Market,
    PaperTrade,
    Signal,
    SignalAntipattern,
    StrategyConfig,
)
from app.modules.antipattern.service import AntipatternModule


@pytest.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as db_session:
        yield db_session
    await engine.dispose()


async def _seed_signal_with_losing_trade(session: AsyncSession) -> Signal:
    strategy = StrategyConfig(
        profile_name="default",
        version=1,
        parameters_json={},
        paper_trading_rules_json={},
        antipattern_rules_json={},
        active_flag=True,
        created_at=datetime(2026, 3, 13, 9, 0, tzinfo=timezone.utc),
    )
    market = Market(
        polymarket_id="pm_anti",
        slug="anti-market",
        title="Antipattern market",
        question="Will antipattern happen?",
        topic="politics",
        status="active",
        watchlist_flag=False,
        blacklist_flag=False,
        archived_flag=False,
    )
    session.add_all([strategy, market])
    await session.flush()

    signal = Signal(
        market_id=market.id,
        snapshot_id=1,
        market_probability=0.5,
        model_probability=0.75,
        edge=0.25,
        confidence=0.85,
        status="paper_trade_candidate",
        explanation="signal",
        risk_flags_json={},
        strategy_config_id=strategy.id,
        strategy_version="default:1",
        created_at=datetime(2026, 3, 13, 10, 0, tzinfo=timezone.utc),
    )
    session.add(signal)
    await session.flush()

    trade = PaperTrade(
        signal_id=signal.id,
        market_id=market.id,
        direction="YES",
        entry_price=0.7,
        position_size=100,
        open_time=datetime(2026, 3, 13, 11, 0, tzinfo=timezone.utc),
        status="closed",
        open_reason="auto",
        strategy_config_id=strategy.id,
        strategy_version="default:1",
        exit_price=0.5,
        close_time=datetime(2026, 3, 13, 12, 0, tzinfo=timezone.utc),
        close_reason="time_limit",
        realized_pnl=-20.0,
    )
    session.add(trade)
    await session.commit()
    return signal


async def test_detect_for_recent_signals_creates_assignment_idempotently(
    session: AsyncSession,
) -> None:
    signal = await _seed_signal_with_losing_trade(session)
    module = AntipatternModule()

    first = await module.detect_for_recent_signals(session=session)
    second = await module.detect_for_recent_signals(session=session)

    assert first == 1
    assert second == 0
    anti_count = await session.scalar(select(func.count()).select_from(Antipattern))
    link_count = await session.scalar(select(func.count()).select_from(SignalAntipattern))
    assert anti_count == 1
    assert link_count == 1
    link = await session.scalar(select(SignalAntipattern))
    assert link is not None
    assert link.signal_id == signal.id

