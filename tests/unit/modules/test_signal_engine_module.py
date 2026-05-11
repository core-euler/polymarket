from datetime import datetime, timezone

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.models import (
    LLMAnalysis,
    Market,
    MarketSnapshot,
    News,
    Signal,
    Source,
    StrategyConfig,
    signal_analyses,
    signal_news,
)
from app.modules.signal_engine.service import SignalEngineModule


@pytest.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as db_session:
        yield db_session
    await engine.dispose()


async def _seed_market_context(session: AsyncSession) -> tuple[Market, MarketSnapshot, News, LLMAnalysis]:
    source = Source(
        name="Source",
        source_type="rss",
        url="https://source.test/rss",
        domain="source.test",
        topic="politics",
        language="en",
        trust_score=0.8,
        priority=1,
        active_flag=True,
    )
    market = Market(
        polymarket_id="pm_signal",
        slug="signal-market",
        title="Signal market",
        question="Will something happen?",
        topic="politics",
        status="active",
        watchlist_flag=False,
        blacklist_flag=False,
        archived_flag=False,
    )
    session.add_all([source, market])
    await session.flush()

    snapshot = MarketSnapshot(
        market_id=market.id,
        captured_at=datetime(2026, 3, 13, 12, 0, tzinfo=timezone.utc),
        last_price=0.5,
        implied_probability=0.5,
        liquidity=1000.0,
        spread=0.02,
        volume=100.0,
        raw_payload={},
    )
    news = News(
        source_id=source.id,
        title="Breaking update",
        url="https://source.test/item",
        published_at=datetime(2026, 3, 13, 11, 0, tzinfo=timezone.utc),
        discovered_at=datetime(2026, 3, 13, 11, 5, tzinfo=timezone.utc),
        summary_text="Summary",
        raw_content="Content",
        language="en",
        content_hash="hash-1",
        topic="politics",
        processing_status="analyzed",
        created_at=datetime(2026, 3, 13, 11, 5, tzinfo=timezone.utc),
    )
    session.add_all([snapshot, news])
    await session.flush()

    analysis = LLMAnalysis(
        news_id=news.id,
        market_id=market.id,
        model_name="test-model",
        prompt_template_version="v1",
        relevance="relevant",
        event_time=datetime(2026, 3, 13, 11, 0, tzinfo=timezone.utc),
        impact_direction="yes",
        impact_strength=0.4,
        confidence=0.8,
        facts_json={},
        entities_json={},
        uncertainties_json={},
        contradictions_json={},
        summary="Likely positive impact",
        trace_json={},
        created_at=datetime(2026, 3, 13, 11, 6, tzinfo=timezone.utc),
    )
    session.add(analysis)
    await session.commit()
    return market, snapshot, news, analysis


async def _seed_active_strategy(session: AsyncSession) -> StrategyConfig:
    strategy = StrategyConfig(
        profile_name="default",
        version=1,
        parameters_json={},
        paper_trading_rules_json={},
        antipattern_rules_json={},
        active_flag=True,
        created_at=datetime(2026, 3, 13, 10, 0, tzinfo=timezone.utc),
    )
    session.add(strategy)
    await session.commit()
    return strategy


async def _seed_active_strategy_with_params(session: AsyncSession, parameters_json: dict) -> StrategyConfig:
    strategy = StrategyConfig(
        profile_name="default",
        version=2,
        parameters_json=parameters_json,
        paper_trading_rules_json={},
        antipattern_rules_json={},
        active_flag=True,
        created_at=datetime(2026, 3, 13, 10, 0, tzinfo=timezone.utc),
    )
    session.add(strategy)
    await session.commit()
    return strategy


async def test_generate_signals_creates_signal_and_links_analysis(session: AsyncSession) -> None:
    market, snapshot, news, analysis = await _seed_market_context(session)
    strategy = await _seed_active_strategy(session)
    module = SignalEngineModule()

    processed = await module.generate_signals(session=session)

    assert processed == 1
    signal = await session.scalar(select(Signal))
    assert signal is not None
    assert signal.market_id == market.id
    assert signal.snapshot_id == snapshot.id
    assert signal.strategy_config_id == strategy.id
    assert signal.model_probability > signal.market_probability
    assert signal.edge > 0
    assert signal.status in {"valid_signal", "paper_trade_candidate", "weak_signal"}

    linked_analysis = await session.scalar(
        select(func.count()).select_from(signal_analyses).where(signal_analyses.c.signal_id == signal.id)
    )
    linked_news = await session.scalar(
        select(func.count()).select_from(signal_news).where(signal_news.c.signal_id == signal.id)
    )
    assert linked_analysis == 1
    assert linked_news == 1
    _ = news
    _ = analysis


async def test_generate_signals_is_idempotent_for_same_snapshot(session: AsyncSession) -> None:
    await _seed_market_context(session)
    await _seed_active_strategy(session)
    module = SignalEngineModule()

    first = await module.generate_signals(session=session)
    second = await module.generate_signals(session=session)

    assert first == 1
    assert second == 0
    total_signals = await session.scalar(select(func.count()).select_from(Signal))
    assert total_signals == 1


async def test_generate_signals_skips_without_active_strategy(session: AsyncSession) -> None:
    await _seed_market_context(session)
    module = SignalEngineModule()

    processed = await module.generate_signals(session=session)

    assert processed == 0
    total_signals = await session.scalar(select(func.count()).select_from(Signal))
    assert total_signals == 0


async def test_generate_signals_applies_min_confidence_threshold(session: AsyncSession) -> None:
    await _seed_market_context(session)
    await _seed_active_strategy_with_params(session, {"min_confidence": 0.9})
    module = SignalEngineModule()

    processed = await module.generate_signals(session=session)

    assert processed == 1
    signal = await session.scalar(select(Signal))
    assert signal is not None
    assert signal.status == "suppressed_by_risk"
    assert signal.risk_flags_json.get("min_confidence") is True


async def test_generate_signals_applies_min_edge_threshold(session: AsyncSession) -> None:
    await _seed_market_context(session)
    await _seed_active_strategy_with_params(session, {"min_edge": 0.2})
    module = SignalEngineModule()

    processed = await module.generate_signals(session=session)

    assert processed == 1
    signal = await session.scalar(select(Signal))
    assert signal is not None
    assert signal.status == "suppressed_by_risk"
    assert signal.risk_flags_json.get("min_edge") is True


async def test_generate_signals_applies_min_liquidity_threshold(session: AsyncSession) -> None:
    await _seed_market_context(session)
    await _seed_active_strategy_with_params(session, {"min_liquidity": 5000})
    module = SignalEngineModule()

    processed = await module.generate_signals(session=session)

    assert processed == 1
    signal = await session.scalar(select(Signal))
    assert signal is not None
    assert signal.status == "suppressed_by_risk"
    assert signal.risk_flags_json.get("min_liquidity") is True


async def test_generate_signals_suppresses_low_probability_extreme(session: AsyncSession) -> None:
    market, snapshot, _, _ = await _seed_market_context(session)
    snapshot.implied_probability = 0.03
    snapshot.last_price = 0.03
    await session.commit()
    await _seed_active_strategy_with_params(session, {"min_market_probability": 0.05})
    module = SignalEngineModule()

    processed = await module.generate_signals(session=session)
    assert processed == 1
    signal = await session.scalar(select(Signal))
    assert signal.status == "suppressed_by_risk"
    assert signal.risk_flags_json.get("min_market_probability") is True
    _ = market


async def test_generate_signals_suppresses_high_probability_extreme(session: AsyncSession) -> None:
    _, snapshot, _, _ = await _seed_market_context(session)
    snapshot.implied_probability = 0.97
    snapshot.last_price = 0.97
    await session.commit()
    await _seed_active_strategy_with_params(session, {"max_market_probability": 0.95})
    module = SignalEngineModule()

    processed = await module.generate_signals(session=session)
    assert processed == 1
    signal = await session.scalar(select(Signal))
    assert signal.status == "suppressed_by_risk"
    assert signal.risk_flags_json.get("max_market_probability") is True


async def test_generate_signals_suppresses_wide_spread(session: AsyncSession) -> None:
    _, snapshot, _, _ = await _seed_market_context(session)
    snapshot.spread = 0.25
    await session.commit()
    await _seed_active_strategy_with_params(session, {"max_allowed_spread": 0.10})
    module = SignalEngineModule()

    processed = await module.generate_signals(session=session)
    assert processed == 1
    signal = await session.scalar(select(Signal))
    assert signal.status == "suppressed_by_risk"
    assert signal.risk_flags_json.get("max_allowed_spread") is True


def test_direction_sign_handles_label_drift() -> None:
    sign = SignalEngineModule._direction_sign
    assert sign("yes") == 1
    assert sign("positive") == 1
    assert sign("INCREASE") == 1
    assert sign("no") == -1
    assert sign("negative") == -1
    assert sign("decrease") == -1
    # ambiguous compounds containing "neutral" are conservatively neutral
    assert sign("neutral_to_slight_negative") == 0
    assert sign("neutral") == 0
    assert sign("mixed") == 0
    assert sign("uncertain") == 0
    assert sign("") == 0
    assert sign(None) == 0


def test_classify_signal_uses_configured_thresholds() -> None:
    # Defaults: paper_trade requires conf>=0.75 and edge>=0.08
    assert (
        SignalEngineModule._classify_signal(edge=0.27, confidence=0.70) == "valid_signal"
    )
    # Loosen via params: now conf>=0.65 and edge>=0.06 should flip to candidate
    relaxed = {
        "paper_trade_confidence_threshold": 0.65,
        "paper_trade_edge_threshold": 0.06,
    }
    assert (
        SignalEngineModule._classify_signal(
            edge=0.27, confidence=0.70, parameters=relaxed
        )
        == "paper_trade_candidate"
    )
    # Tighten weak threshold via params
    tight = {"weak_confidence_threshold": 0.80}
    assert (
        SignalEngineModule._classify_signal(
            edge=0.20, confidence=0.70, parameters=tight
        )
        == "weak_signal"
    )
