from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.models import ErrorReview, Market, PaperTrade, Signal, StrategyConfig
from app.modules.analytics.service import AnalyticsModule


@pytest.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as db_session:
        yield db_session
    await engine.dispose()


async def test_refresh_aggregates_returns_nonzero_processed_count(session: AsyncSession) -> None:
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
        polymarket_id="pm_analytics",
        slug="analytics-market",
        title="Analytics market",
        question="Will analytics happen?",
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
        model_probability=0.6,
        edge=0.1,
        confidence=0.7,
        status="valid_signal",
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
        entry_price=0.55,
        position_size=100,
        open_time=datetime(2026, 3, 13, 11, 0, tzinfo=timezone.utc),
        status="closed",
        open_reason="auto",
        strategy_config_id=strategy.id,
        strategy_version="default:1",
        exit_price=0.6,
        close_time=datetime(2026, 3, 13, 12, 0, tzinfo=timezone.utc),
        close_reason="time_limit",
        realized_pnl=5.0,
    )
    review = ErrorReview(
        review_target_type="paper_trade",
        review_target_id=1,
        error_type="negative_pnl",
        severity="low",
        origin="auto",
        comment="",
        created_by_user_id=None,
        created_at=datetime(2026, 3, 13, 12, 5, tzinfo=timezone.utc),
    )
    session.add_all([trade, review])
    await session.commit()

    module = AnalyticsModule()
    processed = await module.refresh_aggregates(session=session)
    assert processed > 0

