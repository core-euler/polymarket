from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.models import LLMDecision, Market, MarketSnapshot, StrategyConfig
from app.modules.llm_scorer.report import build_report
from app.modules.llm_scorer.service import LLMScorerModule


@pytest.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as db_session:
        yield db_session
    await engine.dispose()


async def _seed_strategy(session: AsyncSession) -> StrategyConfig:
    strategy = StrategyConfig(
        profile_name="default",
        version=5,
        parameters_json={},
        paper_trading_rules_json={},
        antipattern_rules_json={},
        active_flag=True,
        created_at=datetime(2026, 5, 23, 10, 0, tzinfo=timezone.utc),
    )
    session.add(strategy)
    await session.commit()
    return strategy


async def _seed_market(session: AsyncSession, pid: str, status: str = "active") -> Market:
    market = Market(
        polymarket_id=pid, slug=pid, title=pid, question=f"Will {pid}?",
        topic="politics", status=status,
    )
    session.add(market)
    await session.flush()
    return market


async def _seed_snapshot(
    session: AsyncSession, market_id: int, price: float, at: datetime
) -> None:
    session.add(
        MarketSnapshot(
            market_id=market_id, captured_at=at, last_price=price,
            implied_probability=price, liquidity=1000, spread=0.02, volume=100,
            raw_payload={},
        )
    )
    await session.flush()


async def _seed_decision(
    session: AsyncSession,
    *,
    strategy_id: int,
    market_id: int,
    decided_at: datetime,
    action: str = "open",
    side: str | None = "YES",
    price_at_decision: float | None = 0.40,
    confidence: float = 0.7,
    **grading: object,
) -> LLMDecision:
    decision = LLMDecision(
        market_id=market_id,
        strategy_config_id=strategy_id,
        decided_at=decided_at,
        action=action,
        side=side,
        size=5.0,
        confidence=confidence,
        rationale="test",
        price_at_decision=price_at_decision,
        model_name="fake",
        trigger_reason="test",
        executed=True,
        **grading,
    )
    session.add(decision)
    await session.flush()
    return decision


# --- price grading ---------------------------------------------------------

async def test_fills_all_horizons_from_nearest_snapshot(session: AsyncSession) -> None:
    strategy = await _seed_strategy(session)
    market = await _seed_market(session, "m1")
    now = datetime.now(timezone.utc)
    decided = now - timedelta(hours=30)  # all horizons elapsed
    await _seed_decision(
        session, strategy_id=strategy.id, market_id=market.id, decided_at=decided,
        price_at_decision=0.40,
    )
    await _seed_snapshot(session, market.id, 0.45, decided + timedelta(hours=1))
    await _seed_snapshot(session, market.id, 0.55, decided + timedelta(hours=4))
    await _seed_snapshot(session, market.id, 0.70, decided + timedelta(hours=24))
    await session.commit()

    result = await LLMScorerModule().run_cycle(session)

    assert result["prices"] == 3
    decision = await session.scalar(select(LLMDecision))
    assert decision.price_t1h == pytest.approx(0.45)
    assert decision.price_t4h == pytest.approx(0.55)
    assert decision.price_t24h == pytest.approx(0.70)


async def test_horizon_not_elapsed_stays_null(session: AsyncSession) -> None:
    strategy = await _seed_strategy(session)
    market = await _seed_market(session, "m1")
    now = datetime.now(timezone.utc)
    decided = now - timedelta(hours=2)  # only t1h has elapsed
    await _seed_decision(
        session, strategy_id=strategy.id, market_id=market.id, decided_at=decided,
    )
    await _seed_snapshot(session, market.id, 0.50, decided + timedelta(hours=1))
    await session.commit()

    result = await LLMScorerModule().run_cycle(session)

    decision = await session.scalar(select(LLMDecision))
    assert decision.price_t1h == pytest.approx(0.50)
    assert decision.price_t4h is None
    assert decision.price_t24h is None
    assert result["prices"] == 1


async def test_no_snapshot_in_tolerance_leaves_null(session: AsyncSession) -> None:
    strategy = await _seed_strategy(session)
    market = await _seed_market(session, "m1")
    now = datetime.now(timezone.utc)
    decided = now - timedelta(hours=30)
    await _seed_decision(
        session, strategy_id=strategy.id, market_id=market.id, decided_at=decided,
    )
    # Snapshot 5h away from the +1h target — outside the 2h tolerance.
    await _seed_snapshot(session, market.id, 0.50, decided + timedelta(hours=6))
    await session.commit()

    await LLMScorerModule().run_cycle(session)

    decision = await session.scalar(select(LLMDecision))
    assert decision.price_t1h is None  # nearest snapshot too far
    assert decision.price_t4h == pytest.approx(0.50)  # within 2h of +4h target


async def test_grading_is_idempotent(session: AsyncSession) -> None:
    strategy = await _seed_strategy(session)
    market = await _seed_market(session, "m1")
    now = datetime.now(timezone.utc)
    decided = now - timedelta(hours=30)
    await _seed_decision(
        session, strategy_id=strategy.id, market_id=market.id, decided_at=decided,
    )
    await _seed_snapshot(session, market.id, 0.45, decided + timedelta(hours=1))
    await session.commit()

    first = await LLMScorerModule().run_cycle(session)
    second = await LLMScorerModule().run_cycle(session)

    assert first["prices"] == 1
    assert second["prices"] == 0  # already filled, not rewritten


# --- resolution grading ----------------------------------------------------

async def test_resolution_inferred_from_terminal_price(session: AsyncSession) -> None:
    strategy = await _seed_strategy(session)
    yes_mkt = await _seed_market(session, "yes", status="closed")
    no_mkt = await _seed_market(session, "no", status="closed")
    amb_mkt = await _seed_market(session, "amb", status="closed")
    open_mkt = await _seed_market(session, "open", status="active")
    now = datetime.now(timezone.utc)
    for mkt in (yes_mkt, no_mkt, amb_mkt, open_mkt):
        await _seed_decision(
            session, strategy_id=strategy.id, market_id=mkt.id, decided_at=now,
        )
    await _seed_snapshot(session, yes_mkt.id, 0.92, now)
    await _seed_snapshot(session, no_mkt.id, 0.08, now)
    await _seed_snapshot(session, amb_mkt.id, 0.50, now)
    await _seed_snapshot(session, open_mkt.id, 0.95, now)
    await session.commit()

    result = await LLMScorerModule().run_cycle(session)

    decisions = {
        d.market_id: d.resolved_outcome
        for d in await session.scalars(select(LLMDecision))
    }
    assert decisions[yes_mkt.id] == "YES"
    assert decisions[no_mkt.id] == "NO"
    assert decisions[amb_mkt.id] is None  # ambiguous → no guess
    assert decisions[open_mkt.id] is None  # market not closed
    assert result["resolutions"] == 2


# --- report ----------------------------------------------------------------

async def test_report_calibration_and_edge_isolation(session: AsyncSession) -> None:
    strategy = await _seed_strategy(session)
    market = await _seed_market(session, "m1")
    now = datetime.now(timezone.utc)
    # core market, YES, high confidence, favorable (0.40 -> 0.60)
    await _seed_decision(
        session, strategy_id=strategy.id, market_id=market.id, decided_at=now,
        side="YES", price_at_decision=0.40, confidence=0.9, price_t24h=0.60,
    )
    # near-resolution market, YES, low confidence, favorable (0.95 -> 0.99... but
    # use 0.90 -> 0.95 to stay representable) — counts as decay-harvest zone
    await _seed_decision(
        session, strategy_id=strategy.id, market_id=market.id, decided_at=now,
        side="YES", price_at_decision=0.90, confidence=0.4, price_t24h=0.95,
    )
    # core market, NO, mid confidence, UNfavorable (price rose against NO)
    await _seed_decision(
        session, strategy_id=strategy.id, market_id=market.id, decided_at=now,
        side="NO", price_at_decision=0.50, confidence=0.6, price_t24h=0.60,
    )
    await session.commit()

    report = await build_report(session)

    assert report["directional_n"] == 3
    assert report["edge"]["near_resolution"]["n"] == 1
    assert report["edge"]["core"]["n"] == 2
    # core: 1 favorable (YES) of 2 → 0.5
    assert report["edge"]["core"]["favorable_rate"] == pytest.approx(0.5)
    # high-confidence band [0.85,1.0) holds the single favorable YES core call
    high_band = next(b for b in report["calibration"] if b["band"].startswith("[0.85"))
    assert high_band["n"] == 1
    assert high_band["favorable_rate"] == pytest.approx(1.0)
