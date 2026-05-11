from datetime import datetime, timezone

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.models import ErrorReview, Market, PaperTrade, Signal, StrategyConfig
from app.modules.error_review.service import ErrorReviewModule


@pytest.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as db_session:
        yield db_session
    await engine.dispose()


async def _seed_loss_trade(session: AsyncSession, confidence: float = 0.8) -> PaperTrade:
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
        polymarket_id="pm_review",
        slug="review-market",
        title="Review market",
        question="Will review happen?",
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
        model_probability=0.7,
        edge=0.2,
        confidence=confidence,
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
        entry_price=0.65,
        position_size=100,
        open_time=datetime(2026, 3, 13, 11, 0, tzinfo=timezone.utc),
        status="closed",
        open_reason="auto",
        strategy_config_id=strategy.id,
        strategy_version="default:1",
        exit_price=0.5,
        close_time=datetime(2026, 3, 13, 12, 0, tzinfo=timezone.utc),
        close_reason="time_limit",
        realized_pnl=-15.0,
    )
    session.add(trade)
    await session.commit()
    return trade


async def test_create_auto_reviews_creates_one_and_is_idempotent(session: AsyncSession) -> None:
    trade = await _seed_loss_trade(session)
    module = ErrorReviewModule()

    first = await module.create_auto_reviews(session=session)
    second = await module.create_auto_reviews(session=session)

    assert first == 1
    assert second == 0
    count = await session.scalar(select(func.count()).select_from(ErrorReview))
    assert count == 1
    review = await session.scalar(select(ErrorReview))
    assert review is not None
    assert review.review_target_type == "paper_trade"
    assert review.review_target_id == trade.id
    assert review.origin == "auto"
    assert review.error_type in {"high_confidence_loss", "negative_pnl"}

