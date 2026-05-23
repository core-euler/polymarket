from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.models import LLMAnalysis, LLMDecision, Market, MarketSnapshot, PaperTrade, StrategyConfig
from app.db.models.entities import VirtualAccount
from app.modules.llm_trader.service import LLMTraderModule


@pytest.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as db_session:
        yield db_session
    await engine.dispose()


class FakeTrader:
    model_name = "fake-trader"

    def __init__(self, result: dict) -> None:
        self.result = result
        self.contexts: list[dict] = []

    async def decide(self, context: dict) -> dict:
        self.contexts.append(context)
        return self.result


# --- seed helpers ----------------------------------------------------------

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


async def _seed_account(session: AsyncSession, balance: float = 100.0) -> VirtualAccount:
    account = VirtualAccount(balance=balance, initial_balance=balance)
    session.add(account)
    await session.commit()
    return account


async def _seed_market(session: AsyncSession, pid: str, status: str = "active") -> Market:
    market = Market(
        polymarket_id=pid,
        slug=pid,
        title=pid,
        question=f"Will {pid}?",
        topic="politics",
        status=status,
    )
    session.add(market)
    await session.flush()
    return market


async def _seed_snapshot(
    session: AsyncSession, market_id: int, price: float, *, at: datetime | None = None
) -> MarketSnapshot:
    snap = MarketSnapshot(
        market_id=market_id,
        captured_at=at or datetime.now(timezone.utc),
        last_price=price,
        implied_probability=price,
        liquidity=1000,
        spread=0.02,
        volume=100,
        raw_payload={},
    )
    session.add(snap)
    await session.flush()
    return snap


async def _seed_analysis(
    session: AsyncSession, market_id: int, *, relevance: str = "relevant", at: datetime | None = None
) -> LLMAnalysis:
    analysis = LLMAnalysis(
        news_id=1,
        market_id=market_id,
        model_name="cheap",
        relevance=relevance,
        impact_direction="neutral",
        impact_strength=0.0,
        confidence=0.0,
        summary="fresh news digest",
        created_at=at or datetime.now(timezone.utc),
    )
    session.add(analysis)
    await session.flush()
    return analysis


async def _seed_open_trade(
    session: AsyncSession,
    *,
    strategy: StrategyConfig,
    market: Market,
    side: str,
    size: float,
    entry: float,
) -> PaperTrade:
    trade = PaperTrade(
        signal_id=None,
        market_id=market.id,
        direction=side,
        entry_price=entry,
        position_size=size,
        open_time=datetime.now(timezone.utc) - timedelta(hours=1),
        status="open",
        open_reason="seed",
        strategy_config_id=strategy.id,
        strategy_version="default:5",
    )
    session.add(trade)
    await session.commit()
    return trade


def _decisions(*items: dict) -> dict:
    return {"decisions": list(items), "portfolio_notes": ""}


# --- tests -----------------------------------------------------------------

async def test_no_dirty_markets_returns_zero_and_skips_llm(session: AsyncSession) -> None:
    await _seed_strategy(session)
    await _seed_account(session)
    market = await _seed_market(session, "calm")
    await _seed_snapshot(session, market.id, 0.5)  # snapshot but no analysis/position
    await session.commit()

    trader = FakeTrader(_decisions())
    module = LLMTraderModule(trader=trader)
    executed = await module.run_cycle(session)

    assert executed == 0
    assert trader.contexts == []  # LLM never called when nothing is dirty


async def test_new_analysis_triggers_open(session: AsyncSession) -> None:
    strategy = await _seed_strategy(session)
    account = await _seed_account(session, balance=100.0)
    market = await _seed_market(session, "openme")
    await _seed_snapshot(session, market.id, 0.40)
    await _seed_analysis(session, market.id)
    await session.commit()

    trader = FakeTrader(
        _decisions(
            {"market_id": market.id, "action": "open", "side": "YES",
             "size": 5, "confidence": 0.7, "rationale": "news bullish"}
        )
    )
    module = LLMTraderModule(trader=trader)
    executed = await module.run_cycle(session)

    assert executed == 1
    trade = await session.scalar(select(PaperTrade).where(PaperTrade.status == "open"))
    assert trade is not None
    assert trade.direction == "YES"
    assert trade.position_size == 5
    assert trade.entry_price == 0.40
    assert trade.signal_id is None

    acct = await session.scalar(select(VirtualAccount))
    assert acct.balance == pytest.approx(95.0)

    log = await session.scalar(select(LLMDecision))
    assert log.executed is True
    assert log.action == "open"
    assert log.paper_trade_id == trade.id
    assert log.trigger_reason == "new_analysis"
    assert log.price_at_decision == pytest.approx(0.40)


async def test_null_price_is_skipped_for_data_integrity(session: AsyncSession) -> None:
    strategy = await _seed_strategy(session)
    account = await _seed_account(session, balance=100.0)
    market = await _seed_market(session, "noprice")
    await _seed_snapshot(session, market.id, 0.0)  # no usable price
    await _seed_analysis(session, market.id)
    await session.commit()

    trader = FakeTrader(
        _decisions(
            {"market_id": market.id, "action": "open", "side": "YES",
             "size": 5, "confidence": 0.7, "rationale": "x"}
        )
    )
    module = LLMTraderModule(trader=trader)
    executed = await module.run_cycle(session)

    assert executed == 0
    assert await session.scalar(select(PaperTrade)) is None
    acct = await session.scalar(select(VirtualAccount))
    assert acct.balance == pytest.approx(100.0)
    log = await session.scalar(select(LLMDecision))
    assert log.executed is False
    assert "null/invalid price" in log.execution_note


async def test_price_move_triggers_close(session: AsyncSession) -> None:
    strategy = await _seed_strategy(session)
    account = await _seed_account(session, balance=95.0)  # 5 already locked in the position
    market = await _seed_market(session, "closeme")
    await _seed_open_trade(session, strategy=strategy, market=market, side="YES", size=5, entry=0.50)
    await _seed_snapshot(session, market.id, 0.60)  # +0.10 move → dirty(price_move)
    await session.commit()

    trader = FakeTrader(
        _decisions(
            {"market_id": market.id, "action": "close", "confidence": 0.6,
             "rationale": "take it"}
        )
    )
    module = LLMTraderModule(trader=trader)
    executed = await module.run_cycle(session)

    assert executed == 1
    trade = await session.scalar(select(PaperTrade))
    assert trade.status == "closed"
    assert trade.close_reason == "llm_close"
    assert trade.realized_pnl == pytest.approx((0.60 - 0.50) * 5)  # +0.5
    acct = await session.scalar(select(VirtualAccount))
    assert acct.balance == pytest.approx(95.0 + 5 + 0.5)  # principal back + pnl
    log = await session.scalar(select(LLMDecision).where(LLMDecision.action == "close"))
    assert log.executed is True and log.trigger_reason == "price_move"


async def test_hold_is_noop_but_logged(session: AsyncSession) -> None:
    strategy = await _seed_strategy(session)
    await _seed_account(session)
    market = await _seed_market(session, "holdme")
    await _seed_snapshot(session, market.id, 0.5)
    await _seed_analysis(session, market.id)
    await session.commit()

    trader = FakeTrader(
        _decisions({"market_id": market.id, "action": "hold", "rationale": "wait"})
    )
    module = LLMTraderModule(trader=trader)
    executed = await module.run_cycle(session)

    assert executed == 0
    assert await session.scalar(select(PaperTrade)) is None
    log = await session.scalar(select(LLMDecision))
    assert log.action == "hold" and log.executed is False


async def test_hallucinated_market_is_ignored(session: AsyncSession) -> None:
    strategy = await _seed_strategy(session)
    await _seed_account(session)
    market = await _seed_market(session, "real")
    await _seed_snapshot(session, market.id, 0.5)
    await _seed_analysis(session, market.id)
    await session.commit()

    trader = FakeTrader(
        _decisions(
            {"market_id": 99999, "action": "open", "side": "YES", "size": 5,
             "rationale": "ghost"}
        )
    )
    module = LLMTraderModule(trader=trader)
    executed = await module.run_cycle(session)

    assert executed == 0
    assert await session.scalar(select(PaperTrade)) is None
    # no decision row for a market that was never in the dirty set
    assert await session.scalar(select(LLMDecision)) is None


async def test_insufficient_balance_skips_open(session: AsyncSession) -> None:
    strategy = await _seed_strategy(session)
    await _seed_account(session, balance=3.0)
    market = await _seed_market(session, "toobig")
    await _seed_snapshot(session, market.id, 0.5)
    await _seed_analysis(session, market.id)
    await session.commit()

    trader = FakeTrader(
        _decisions(
            {"market_id": market.id, "action": "open", "side": "YES", "size": 5,
             "rationale": "x"}
        )
    )
    module = LLMTraderModule(trader=trader)
    executed = await module.run_cycle(session)

    assert executed == 0
    assert await session.scalar(select(PaperTrade)) is None
    log = await session.scalar(select(LLMDecision))
    assert "insufficient balance" in log.execution_note


async def test_open_on_already_open_market_is_skipped(session: AsyncSession) -> None:
    strategy = await _seed_strategy(session)
    await _seed_account(session, balance=95.0)
    market = await _seed_market(session, "dup")
    await _seed_open_trade(session, strategy=strategy, market=market, side="YES", size=5, entry=0.50)
    await _seed_snapshot(session, market.id, 0.60)  # price move → dirty
    await session.commit()

    trader = FakeTrader(
        _decisions(
            {"market_id": market.id, "action": "open", "side": "NO", "size": 5,
             "rationale": "wrong tool"}
        )
    )
    module = LLMTraderModule(trader=trader)
    executed = await module.run_cycle(session)

    assert executed == 0
    open_trades = list(await session.scalars(select(PaperTrade).where(PaperTrade.status == "open")))
    assert len(open_trades) == 1  # original untouched
    log = await session.scalar(select(LLMDecision))
    assert "already open" in log.execution_note


async def test_adjust_replaces_existing_position(session: AsyncSession) -> None:
    strategy = await _seed_strategy(session)
    await _seed_account(session, balance=95.0)
    market = await _seed_market(session, "flip")
    await _seed_open_trade(session, strategy=strategy, market=market, side="YES", size=5, entry=0.50)
    await _seed_snapshot(session, market.id, 0.60)  # price move → dirty
    await session.commit()

    trader = FakeTrader(
        _decisions(
            {"market_id": market.id, "action": "adjust", "side": "NO", "size": 8,
             "confidence": 0.8, "rationale": "flip and size up"}
        )
    )
    module = LLMTraderModule(trader=trader)
    executed = await module.run_cycle(session)

    assert executed == 1
    closed = list(await session.scalars(select(PaperTrade).where(PaperTrade.status == "closed")))
    opened = list(await session.scalars(select(PaperTrade).where(PaperTrade.status == "open")))
    assert len(closed) == 1 and closed[0].close_reason == "llm_adjust"
    assert len(opened) == 1
    assert opened[0].direction == "NO" and opened[0].position_size == 8
    assert opened[0].entry_price == pytest.approx(0.60)


async def test_retired_modules_are_inert() -> None:
    from app.modules.paper_trading.service import PaperTradingModule
    from app.modules.signal_engine.service import SignalEngineModule

    assert await SignalEngineModule().generate_signals(None) == 0
    assert await PaperTradingModule().open_eligible_trades(None) == 0
    assert await PaperTradingModule().monitor_open_trades(None) == 0
