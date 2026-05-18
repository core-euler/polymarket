from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.models import Market, MarketSnapshot, PaperTrade, Signal, StrategyConfig
from app.db.models.entities import VirtualAccount
from app.modules.paper_trading.service import PaperTradingModule


@pytest.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as db_session:
        yield db_session
    await engine.dispose()


async def _seed_strategy(session: AsyncSession, max_holding_minutes: int = 60) -> StrategyConfig:
    strategy = StrategyConfig(
        profile_name="default",
        version=1,
        parameters_json={"default_position_size": 100},
        paper_trading_rules_json={"max_holding_minutes": max_holding_minutes},
        antipattern_rules_json={},
        active_flag=True,
        created_at=datetime(2026, 3, 13, 10, 0, tzinfo=timezone.utc),
    )
    session.add(strategy)
    await session.commit()
    return strategy


async def _seed_market_and_signal(
    session: AsyncSession,
    strategy: StrategyConfig,
    status: str = "paper_trade_candidate",
    edge: float = 0.12,
) -> tuple[Market, Signal]:
    market = Market(
        polymarket_id="pm_trade",
        slug="trade-market",
        title="Trade market",
        question="Will trade happen?",
        topic="politics",
        status="active",
        watchlist_flag=False,
        blacklist_flag=False,
        archived_flag=False,
    )
    session.add(market)
    await session.flush()

    snapshot = MarketSnapshot(
        market_id=market.id,
        captured_at=datetime(2026, 3, 13, 12, 0, tzinfo=timezone.utc),
        last_price=0.5,
        implied_probability=0.5,
        liquidity=1000,
        spread=0.02,
        volume=100,
        raw_payload={},
    )
    session.add(snapshot)
    await session.flush()

    signal = Signal(
        market_id=market.id,
        snapshot_id=snapshot.id,
        market_probability=0.5,
        model_probability=0.62 if edge >= 0 else 0.38,
        edge=edge,
        confidence=0.8,
        status=status,
        explanation="signal",
        risk_flags_json={},
        strategy_config_id=strategy.id,
        strategy_version="default:1",
        created_at=datetime(2026, 3, 13, 12, 1, tzinfo=timezone.utc),
    )
    session.add(signal)
    await session.commit()
    return market, signal


async def _seed_virtual_account(session: AsyncSession, balance: float = 1000.0) -> VirtualAccount:
    account = VirtualAccount(balance=balance, initial_balance=balance)
    session.add(account)
    await session.commit()
    return account


async def _seed_bare_market(session: AsyncSession, pid: str) -> Market:
    market = Market(
        polymarket_id=pid,
        slug=pid,
        title=pid,
        question="Q?",
        topic="politics",
        status="active",
    )
    session.add(market)
    await session.flush()
    return market


async def _seed_existing_trade(
    session: AsyncSession,
    *,
    strategy: StrategyConfig,
    market: Market,
    direction: str,
    status: str,
    realized_pnl: float | None = None,
    open_time: datetime | None = None,
    close_time: datetime | None = None,
) -> PaperTrade:
    # PaperTrade.signal_id is non-nullable — attach a throwaway signal/snapshot.
    snapshot = MarketSnapshot(
        market_id=market.id,
        captured_at=datetime.now(timezone.utc),
        last_price=0.5,
        implied_probability=0.5,
        liquidity=1000,
        spread=0.02,
        volume=10,
        raw_payload={},
    )
    session.add(snapshot)
    await session.flush()
    sig = Signal(
        market_id=market.id,
        snapshot_id=snapshot.id,
        market_probability=0.5,
        model_probability=0.6,
        edge=0.1,
        confidence=0.8,
        status="paper_trade_candidate",
        explanation="seed",
        risk_flags_json={},
        strategy_config_id=strategy.id,
        strategy_version="default:1",
        created_at=datetime.now(timezone.utc),
    )
    session.add(sig)
    await session.flush()
    trade = PaperTrade(
        signal_id=sig.id,
        market_id=market.id,
        direction=direction,
        entry_price=0.5,
        position_size=1.0,
        open_time=open_time or datetime.now(timezone.utc),
        status=status,
        open_reason="seed",
        strategy_config_id=strategy.id,
        strategy_version="default:1",
        close_time=close_time,
        realized_pnl=realized_pnl,
        close_reason="seed" if status == "closed" else None,
    )
    session.add(trade)
    await session.flush()
    return trade


def _risk_strategy(rules: dict) -> StrategyConfig:
    return StrategyConfig(
        profile_name="default",
        version=4,
        parameters_json={"default_position_size": 1.0},
        paper_trading_rules_json={"auto_paper_trade_enabled": True, **rules},
        antipattern_rules_json={},
        active_flag=True,
        created_at=datetime(2026, 5, 18, 10, 0, tzinfo=timezone.utc),
    )


async def test_open_eligible_trades_creates_trade_once(session: AsyncSession) -> None:
    strategy = await _seed_strategy(session)
    await _seed_virtual_account(session, balance=1000.0)
    _market, signal = await _seed_market_and_signal(session, strategy=strategy)
    module = PaperTradingModule()

    first = await module.open_eligible_trades(session=session)
    second = await module.open_eligible_trades(session=session)

    assert first == 1
    assert second == 0
    trades = list(await session.scalars(select(PaperTrade)))
    assert len(trades) == 1
    assert trades[0].signal_id == signal.id
    assert trades[0].status == "open"
    assert trades[0].direction == "YES"


async def test_open_eligible_trades_respects_eligible_statuses(session: AsyncSession) -> None:
    strategy = StrategyConfig(
        profile_name="default",
        version=1,
        parameters_json={"default_position_size": 100},
        paper_trading_rules_json={
            "auto_paper_trade_enabled": True,
            "eligible_signal_statuses": ["paper_trade_candidate", "valid_signal"],
        },
        antipattern_rules_json={},
        active_flag=True,
        created_at=datetime(2026, 3, 13, 10, 0, tzinfo=timezone.utc),
    )
    session.add(strategy)
    await session.commit()
    await _seed_virtual_account(session, balance=1000.0)
    _market, signal = await _seed_market_and_signal(
        session, strategy=strategy, status="valid_signal", edge=-0.2
    )
    module = PaperTradingModule()

    opened = await module.open_eligible_trades(session=session)

    assert opened == 1
    trade = await session.scalar(select(PaperTrade).where(PaperTrade.signal_id == signal.id))
    assert trade is not None
    assert trade.direction == "NO"


async def test_open_eligible_trades_skipped_when_auto_disabled(session: AsyncSession) -> None:
    strategy = StrategyConfig(
        profile_name="default",
        version=1,
        parameters_json={"default_position_size": 100},
        paper_trading_rules_json={"auto_paper_trade_enabled": False},
        antipattern_rules_json={},
        active_flag=True,
        created_at=datetime(2026, 3, 13, 10, 0, tzinfo=timezone.utc),
    )
    session.add(strategy)
    await session.commit()
    await _seed_virtual_account(session, balance=1000.0)
    await _seed_market_and_signal(session, strategy=strategy, status="paper_trade_candidate")
    module = PaperTradingModule()

    opened = await module.open_eligible_trades(session=session)

    assert opened == 0
    assert list(await session.scalars(select(PaperTrade))) == []


async def test_open_eligible_trades_dedupes_per_market(session: AsyncSession) -> None:
    strategy = await _seed_strategy(session)
    await _seed_virtual_account(session, balance=1000.0)
    market, first_signal = await _seed_market_and_signal(session, strategy=strategy)

    second_snapshot = MarketSnapshot(
        market_id=market.id,
        captured_at=datetime(2026, 3, 13, 13, 0, tzinfo=timezone.utc),
        last_price=0.55,
        implied_probability=0.55,
        liquidity=1100,
        spread=0.02,
        volume=130,
        raw_payload={},
    )
    session.add(second_snapshot)
    await session.flush()
    second_signal = Signal(
        market_id=market.id,
        snapshot_id=second_snapshot.id,
        market_probability=0.55,
        model_probability=0.65,
        edge=0.10,
        confidence=0.8,
        status="paper_trade_candidate",
        explanation="second",
        risk_flags_json={},
        strategy_config_id=strategy.id,
        strategy_version="default:1",
        created_at=datetime(2026, 3, 13, 13, 1, tzinfo=timezone.utc),
    )
    session.add(second_signal)
    await session.commit()

    module = PaperTradingModule()
    opened = await module.open_eligible_trades(session=session)

    assert opened == 1
    trades = list(await session.scalars(select(PaperTrade)))
    assert len(trades) == 1
    assert trades[0].signal_id == first_signal.id


async def test_monitor_open_trades_closes_on_take_profit(session: AsyncSession) -> None:
    strategy = StrategyConfig(
        profile_name="default",
        version=1,
        parameters_json={"default_position_size": 100},
        paper_trading_rules_json={
            "auto_paper_trade_enabled": True,
            "max_holding_minutes": 999999,
            "take_profit_pct": 0.10,
            "stop_loss_pct": 0.20,
        },
        antipattern_rules_json={},
        active_flag=True,
        created_at=datetime(2026, 3, 13, 10, 0, tzinfo=timezone.utc),
    )
    session.add(strategy)
    await session.commit()
    await _seed_virtual_account(session, balance=1000.0)
    market, _ = await _seed_market_and_signal(session, strategy=strategy)
    module = PaperTradingModule()
    await module.open_eligible_trades(session=session)

    new_snapshot = MarketSnapshot(
        market_id=market.id,
        captured_at=datetime.now(timezone.utc),
        last_price=0.6,  # YES bought at 0.5, now 0.6 → +20% > take_profit_pct=10%
        implied_probability=0.6,
        liquidity=1000,
        spread=0.02,
        volume=120,
        raw_payload={},
    )
    session.add(new_snapshot)
    await session.commit()

    closed = await module.monitor_open_trades(session=session)

    assert closed == 1
    trade = await session.scalar(select(PaperTrade))
    assert trade.status == "closed"
    assert trade.close_reason == "take_profit"
    assert trade.exit_price == 0.6


async def test_monitor_open_trades_closes_on_stop_loss(session: AsyncSession) -> None:
    strategy = StrategyConfig(
        profile_name="default",
        version=1,
        parameters_json={"default_position_size": 100},
        paper_trading_rules_json={
            "auto_paper_trade_enabled": True,
            "max_holding_minutes": 999999,
            "take_profit_pct": 0.30,
            "stop_loss_pct": 0.10,
        },
        antipattern_rules_json={},
        active_flag=True,
        created_at=datetime(2026, 3, 13, 10, 0, tzinfo=timezone.utc),
    )
    session.add(strategy)
    await session.commit()
    await _seed_virtual_account(session, balance=1000.0)
    market, _ = await _seed_market_and_signal(session, strategy=strategy)
    module = PaperTradingModule()
    await module.open_eligible_trades(session=session)

    new_snapshot = MarketSnapshot(
        market_id=market.id,
        captured_at=datetime.now(timezone.utc),
        last_price=0.4,  # YES at 0.5 → 0.4 → -20% past stop_loss_pct=10%
        implied_probability=0.4,
        liquidity=1000,
        spread=0.02,
        volume=120,
        raw_payload={},
    )
    session.add(new_snapshot)
    await session.commit()

    closed = await module.monitor_open_trades(session=session)

    assert closed == 1
    trade = await session.scalar(select(PaperTrade))
    assert trade.status == "closed"
    assert trade.close_reason == "stop_loss"
    assert trade.exit_price == 0.4


async def test_monitor_open_trades_take_profit_abs_wins_over_pct(session: AsyncSession) -> None:
    # Bug regression: low-priced market (entry 0.07) used to trip on noise because
    # take_profit_pct is relative to entry. Absolute threshold treats entry-level
    # uniformly: 10 ppt move means the same at 0.07 and 0.55.
    strategy = StrategyConfig(
        profile_name="default",
        version=1,
        parameters_json={"default_position_size": 100},
        paper_trading_rules_json={
            "auto_paper_trade_enabled": True,
            "max_holding_minutes": 999999,
            "take_profit_abs": 0.10,
            "stop_loss_abs": 0.07,
            # _pct values present but should be ignored when _abs is set
            "take_profit_pct": 0.15,
            "stop_loss_pct": 0.10,
        },
        antipattern_rules_json={},
        active_flag=True,
        created_at=datetime(2026, 3, 13, 10, 0, tzinfo=timezone.utc),
    )
    session.add(strategy)
    await session.commit()
    await _seed_virtual_account(session, balance=1000.0)

    market = Market(
        polymarket_id="pm_low",
        slug="low",
        title="Low",
        question="Low?",
        topic="politics",
        status="active",
    )
    session.add(market)
    await session.flush()
    snapshot = MarketSnapshot(
        market_id=market.id,
        captured_at=datetime(2026, 3, 13, 12, 0, tzinfo=timezone.utc),
        last_price=0.07,
        implied_probability=0.07,
        liquidity=1000,
        spread=0.02,
        volume=100,
        raw_payload={},
    )
    session.add(snapshot)
    await session.flush()
    signal = Signal(
        market_id=market.id,
        snapshot_id=snapshot.id,
        market_probability=0.07,
        model_probability=0.18,
        edge=0.11,
        confidence=0.8,
        status="paper_trade_candidate",
        explanation="low entry",
        risk_flags_json={},
        strategy_config_id=strategy.id,
        strategy_version="default:1",
        created_at=datetime(2026, 3, 13, 12, 1, tzinfo=timezone.utc),
    )
    session.add(signal)
    await session.commit()

    module = PaperTradingModule()
    await module.open_eligible_trades(session=session)

    # Move mark by +0.05 (≈70% relative — would trip pct, must NOT trip abs at 0.10)
    new_snapshot = MarketSnapshot(
        market_id=market.id,
        captured_at=datetime.now(timezone.utc),
        last_price=0.12,
        implied_probability=0.12,
        liquidity=1000,
        spread=0.02,
        volume=100,
        raw_payload={},
    )
    session.add(new_snapshot)
    await session.commit()

    closed = await module.monitor_open_trades(session=session)
    assert closed == 0
    trade = await session.scalar(select(PaperTrade))
    assert trade.status == "open"

    # Now jump beyond abs threshold: 0.07 → 0.20 (+0.13 ≥ 0.10)
    bigger_snapshot = MarketSnapshot(
        market_id=market.id,
        captured_at=datetime.now(timezone.utc),
        last_price=0.20,
        implied_probability=0.20,
        liquidity=1000,
        spread=0.02,
        volume=100,
        raw_payload={},
    )
    session.add(bigger_snapshot)
    await session.commit()

    closed = await module.monitor_open_trades(session=session)
    assert closed == 1
    trade = await session.scalar(select(PaperTrade))
    assert trade.close_reason == "take_profit"


async def test_monitor_open_trades_stop_loss_abs(session: AsyncSession) -> None:
    strategy = StrategyConfig(
        profile_name="default",
        version=1,
        parameters_json={"default_position_size": 100},
        paper_trading_rules_json={
            "auto_paper_trade_enabled": True,
            "max_holding_minutes": 999999,
            "take_profit_abs": 0.20,
            "stop_loss_abs": 0.05,
        },
        antipattern_rules_json={},
        active_flag=True,
        created_at=datetime(2026, 3, 13, 10, 0, tzinfo=timezone.utc),
    )
    session.add(strategy)
    await session.commit()
    await _seed_virtual_account(session, balance=1000.0)
    market, _ = await _seed_market_and_signal(session, strategy=strategy)
    module = PaperTradingModule()
    await module.open_eligible_trades(session=session)

    # YES bought at 0.5 → 0.43 means -0.07 ≤ -0.05 → stop_loss
    new_snapshot = MarketSnapshot(
        market_id=market.id,
        captured_at=datetime.now(timezone.utc),
        last_price=0.43,
        implied_probability=0.43,
        liquidity=1000,
        spread=0.02,
        volume=120,
        raw_payload={},
    )
    session.add(new_snapshot)
    await session.commit()

    closed = await module.monitor_open_trades(session=session)
    assert closed == 1
    trade = await session.scalar(select(PaperTrade))
    assert trade.close_reason == "stop_loss"
    assert trade.exit_price == 0.43


async def test_open_eligible_trades_skips_signals_from_deprecated_strategy(
    session: AsyncSession,
) -> None:
    # Bug regression: bumping to v2 left v1 signals in the DB still eligible,
    # so paper_trades kept opening with the broken old probability bounds.
    legacy = StrategyConfig(
        profile_name="default",
        version=1,
        parameters_json={"default_position_size": 100},
        paper_trading_rules_json={"auto_paper_trade_enabled": True},
        antipattern_rules_json={},
        active_flag=False,
        created_at=datetime(2026, 3, 13, 9, 0, tzinfo=timezone.utc),
    )
    session.add(legacy)
    await session.commit()

    active = StrategyConfig(
        profile_name="default",
        version=2,
        parameters_json={"default_position_size": 100},
        paper_trading_rules_json={"auto_paper_trade_enabled": True},
        antipattern_rules_json={},
        active_flag=True,
        created_at=datetime(2026, 3, 13, 10, 0, tzinfo=timezone.utc),
    )
    session.add(active)
    await session.commit()
    await _seed_virtual_account(session, balance=1000.0)

    market = Market(
        polymarket_id="pm_legacy",
        slug="legacy",
        title="Legacy",
        question="Q?",
        topic="politics",
        status="active",
    )
    session.add(market)
    await session.flush()
    snapshot = MarketSnapshot(
        market_id=market.id,
        captured_at=datetime(2026, 3, 13, 12, 0, tzinfo=timezone.utc),
        last_price=0.001,  # extreme — exactly the kind v1 missed and v2 catches
        implied_probability=0.001,
        liquidity=1000,
        spread=0.02,
        volume=100,
        raw_payload={},
    )
    session.add(snapshot)
    await session.flush()
    legacy_signal = Signal(
        market_id=market.id,
        snapshot_id=snapshot.id,
        market_probability=0.001,
        model_probability=0.10,
        edge=0.099,
        confidence=0.8,
        status="paper_trade_candidate",
        explanation="legacy v1 with extreme entry",
        risk_flags_json={},
        strategy_config_id=legacy.id,
        strategy_version="default:1",
        created_at=datetime(2026, 3, 13, 12, 1, tzinfo=timezone.utc),
    )
    session.add(legacy_signal)
    await session.commit()

    module = PaperTradingModule()
    opened = await module.open_eligible_trades(session=session)

    assert opened == 0
    assert list(await session.scalars(select(PaperTrade))) == []


async def test_monitor_open_trades_uses_live_active_strategy(
    session: AsyncSession,
) -> None:
    # Bug regression: trade opened under v1 (take_profit_pct=0.15) must close
    # using v2 absolute rules (take_profit_abs=0.10), not the broken v1 pct.
    legacy = StrategyConfig(
        profile_name="default",
        version=1,
        parameters_json={"default_position_size": 100},
        paper_trading_rules_json={
            "auto_paper_trade_enabled": True,
            "max_holding_minutes": 999999,
            "take_profit_pct": 0.15,
            "stop_loss_pct": 0.10,
        },
        antipattern_rules_json={},
        active_flag=False,
        created_at=datetime(2026, 3, 13, 9, 0, tzinfo=timezone.utc),
    )
    session.add(legacy)
    await session.commit()

    active = StrategyConfig(
        profile_name="default",
        version=2,
        parameters_json={"default_position_size": 100},
        paper_trading_rules_json={
            "auto_paper_trade_enabled": True,
            "max_holding_minutes": 999999,
            "take_profit_abs": 0.10,
            "stop_loss_abs": 0.05,
        },
        antipattern_rules_json={},
        active_flag=True,
        created_at=datetime(2026, 3, 13, 10, 0, tzinfo=timezone.utc),
    )
    session.add(active)
    await session.commit()
    await _seed_virtual_account(session, balance=1000.0)

    market = Market(
        polymarket_id="pm_legacy_open",
        slug="legacy-open",
        title="Legacy still open",
        question="Q?",
        topic="politics",
        status="active",
    )
    session.add(market)
    await session.flush()
    snapshot = MarketSnapshot(
        market_id=market.id,
        captured_at=datetime(2026, 3, 13, 12, 0, tzinfo=timezone.utc),
        last_price=0.075,
        implied_probability=0.075,
        liquidity=1000,
        spread=0.02,
        volume=100,
        raw_payload={},
    )
    session.add(snapshot)
    await session.flush()

    # Manually create the trade as if it had been opened under v1.
    trade = PaperTrade(
        signal_id=None,
        market_id=market.id,
        direction="YES",
        entry_price=0.075,
        position_size=100,
        open_time=datetime.now(timezone.utc),
        status="open",
        open_reason="legacy_v1",
        strategy_config_id=legacy.id,
        strategy_version="default:1",
    )
    # PaperTrade.signal_id is non-nullable; cheat by attaching a real signal.
    legacy_signal = Signal(
        market_id=market.id,
        snapshot_id=snapshot.id,
        market_probability=0.075,
        model_probability=0.18,
        edge=0.105,
        confidence=0.8,
        status="paper_trade_candidate",
        explanation="legacy",
        risk_flags_json={},
        strategy_config_id=legacy.id,
        strategy_version="default:1",
        created_at=datetime(2026, 3, 13, 12, 1, tzinfo=timezone.utc),
    )
    session.add(legacy_signal)
    await session.flush()
    trade.signal_id = legacy_signal.id
    session.add(trade)
    await session.commit()

    # +0.05 move (≈67% relative): would trip v1 pct=0.15, must NOT trip v2 abs=0.10.
    new_snapshot = MarketSnapshot(
        market_id=market.id,
        captured_at=datetime.now(timezone.utc),
        last_price=0.125,
        implied_probability=0.125,
        liquidity=1000,
        spread=0.02,
        volume=110,
        raw_payload={},
    )
    session.add(new_snapshot)
    await session.commit()

    module = PaperTradingModule()
    closed = await module.monitor_open_trades(session=session)

    assert closed == 0
    refreshed = await session.scalar(select(PaperTrade).where(PaperTrade.id == trade.id))
    assert refreshed.status == "open"


async def test_monitor_open_trades_skips_suspicious_jump_far_from_expiry(
    session: AsyncSession,
) -> None:
    # Bug regression: snapshot jumped from 0.5 to 1.0 on a market that does
    # not resolve for months. Must NOT close — wait for the next tick instead.
    strategy = StrategyConfig(
        profile_name="default",
        version=1,
        parameters_json={"default_position_size": 100},
        paper_trading_rules_json={
            "auto_paper_trade_enabled": True,
            "max_holding_minutes": 999999,
            "take_profit_abs": 0.10,
            "max_mark_jump_per_tick": 0.4,
        },
        antipattern_rules_json={},
        active_flag=True,
        created_at=datetime(2026, 3, 13, 10, 0, tzinfo=timezone.utc),
    )
    session.add(strategy)
    await session.commit()
    await _seed_virtual_account(session, balance=1000.0)
    market, _ = await _seed_market_and_signal(session, strategy=strategy)
    market.expires_at = datetime.now(timezone.utc) + timedelta(days=60)
    await session.commit()

    module = PaperTradingModule()
    await module.open_eligible_trades(session=session)

    bad_snapshot = MarketSnapshot(
        market_id=market.id,
        captured_at=datetime.now(timezone.utc),
        last_price=1.0,
        implied_probability=1.0,
        liquidity=1000,
        spread=0.02,
        volume=120,
        raw_payload={},
    )
    session.add(bad_snapshot)
    await session.commit()

    closed = await module.monitor_open_trades(session=session)
    assert closed == 0
    trade = await session.scalar(select(PaperTrade))
    assert trade.status == "open"


async def test_monitor_open_trades_allows_jump_near_expiry(session: AsyncSession) -> None:
    # If the market is about to resolve, a large jump is plausible — let it close.
    strategy = StrategyConfig(
        profile_name="default",
        version=1,
        parameters_json={"default_position_size": 100},
        paper_trading_rules_json={
            "auto_paper_trade_enabled": True,
            "max_holding_minutes": 999999,
            "take_profit_abs": 0.10,
            "max_mark_jump_per_tick": 0.4,
        },
        antipattern_rules_json={},
        active_flag=True,
        created_at=datetime(2026, 3, 13, 10, 0, tzinfo=timezone.utc),
    )
    session.add(strategy)
    await session.commit()
    await _seed_virtual_account(session, balance=1000.0)
    market, _ = await _seed_market_and_signal(session, strategy=strategy)
    market.expires_at = datetime.now(timezone.utc) + timedelta(hours=2)
    await session.commit()

    module = PaperTradingModule()
    await module.open_eligible_trades(session=session)

    near_resolve = MarketSnapshot(
        market_id=market.id,
        captured_at=datetime.now(timezone.utc),
        last_price=1.0,
        implied_probability=1.0,
        liquidity=1000,
        spread=0.02,
        volume=120,
        raw_payload={},
    )
    session.add(near_resolve)
    await session.commit()

    closed = await module.monitor_open_trades(session=session)
    assert closed == 1
    trade = await session.scalar(select(PaperTrade))
    assert trade.close_reason == "take_profit"


async def test_monitor_open_trades_closes_by_time_limit(session: AsyncSession) -> None:
    strategy = await _seed_strategy(session, max_holding_minutes=1)
    await _seed_virtual_account(session, balance=1000.0)
    market, signal = await _seed_market_and_signal(session, strategy=strategy)
    module = PaperTradingModule()
    await module.open_eligible_trades(session=session)

    trade = await session.scalar(select(PaperTrade).where(PaperTrade.signal_id == signal.id))
    assert trade is not None
    trade.open_time = datetime.now(timezone.utc) - timedelta(minutes=5)
    await session.commit()

    new_snapshot = MarketSnapshot(
        market_id=market.id,
        captured_at=datetime.now(timezone.utc),
        last_price=0.56,
        implied_probability=0.56,
        liquidity=1000,
        spread=0.02,
        volume=120,
        raw_payload={},
    )
    session.add(new_snapshot)
    await session.commit()

    closed_count = await module.monitor_open_trades(session=session)

    assert closed_count == 1
    refreshed = await session.scalar(select(PaperTrade).where(PaperTrade.id == trade.id))
    assert refreshed is not None
    assert refreshed.status == "closed"
    assert refreshed.close_reason == "time_limit"
    assert refreshed.exit_price == 0.56
    assert refreshed.realized_pnl is not None


# --- Risk layer (v4) regression tests --------------------------------------
# v3 (1052 trades / 6 days) had no portfolio risk control: ~371 trades serially
# churned on ONE decaying market, and one risk-off day lost -$11.56 with 384 SL
# at once. These guards cap per-market churn, halt on a daily loss budget, and
# stop the book becoming a single one-way bet. All are config-gated.


async def test_open_eligible_trades_caps_trades_per_market_per_day(
    session: AsyncSession,
) -> None:
    strategy = _risk_strategy({"max_trades_per_market_per_day": 2})
    session.add(strategy)
    await session.commit()
    await _seed_virtual_account(session, balance=1000.0)
    market, signal = await _seed_market_and_signal(session, strategy=strategy)
    # Two trades already initiated on THIS market today (closed) → at the cap.
    for _ in range(2):
        await _seed_existing_trade(
            session,
            strategy=strategy,
            market=market,
            direction="YES",
            status="closed",
            realized_pnl=0.0,
            close_time=datetime.now(timezone.utc),
        )
    await session.commit()

    module = PaperTradingModule()
    opened = await module.open_eligible_trades(session=session)

    assert opened == 0
    assert (
        await session.scalar(
            select(PaperTrade).where(PaperTrade.signal_id == signal.id)
        )
        is None
    )


async def test_open_eligible_trades_per_market_cap_allows_under_limit(
    session: AsyncSession,
) -> None:
    strategy = _risk_strategy({"max_trades_per_market_per_day": 3})
    session.add(strategy)
    await session.commit()
    await _seed_virtual_account(session, balance=1000.0)
    market, signal = await _seed_market_and_signal(session, strategy=strategy)
    # Only one prior (closed) trade today — still under the cap of 3.
    await _seed_existing_trade(
        session,
        strategy=strategy,
        market=market,
        direction="YES",
        status="closed",
        realized_pnl=0.0,
        close_time=datetime.now(timezone.utc),
    )
    await session.commit()

    module = PaperTradingModule()
    opened = await module.open_eligible_trades(session=session)

    assert opened == 1
    trade = await session.scalar(
        select(PaperTrade).where(PaperTrade.signal_id == signal.id)
    )
    assert trade is not None and trade.status == "open"


async def test_open_eligible_trades_halts_on_daily_loss_limit(
    session: AsyncSession,
) -> None:
    strategy = _risk_strategy({"daily_loss_limit_abs": 1.0})
    session.add(strategy)
    await session.commit()
    await _seed_virtual_account(session, balance=1000.0)
    _market, signal = await _seed_market_and_signal(session, strategy=strategy)
    losers = await _seed_bare_market(session, "pm_losers")
    # Realized PnL today = -1.5 ≤ -daily_loss_limit_abs(1.0) → halt new opens.
    await _seed_existing_trade(
        session,
        strategy=strategy,
        market=losers,
        direction="NO",
        status="closed",
        realized_pnl=-1.5,
        close_time=datetime.now(timezone.utc),
    )
    await session.commit()

    module = PaperTradingModule()
    opened = await module.open_eligible_trades(session=session)

    assert opened == 0
    assert (
        await session.scalar(
            select(PaperTrade).where(PaperTrade.signal_id == signal.id)
        )
        is None
    )


async def test_open_eligible_trades_opens_when_under_daily_loss_limit(
    session: AsyncSession,
) -> None:
    strategy = _risk_strategy({"daily_loss_limit_abs": 1.0})
    session.add(strategy)
    await session.commit()
    await _seed_virtual_account(session, balance=1000.0)
    _market, signal = await _seed_market_and_signal(session, strategy=strategy)
    losers = await _seed_bare_market(session, "pm_losers")
    # -0.5 is above the -1.0 budget → trading continues.
    await _seed_existing_trade(
        session,
        strategy=strategy,
        market=losers,
        direction="NO",
        status="closed",
        realized_pnl=-0.5,
        close_time=datetime.now(timezone.utc),
    )
    await session.commit()

    module = PaperTradingModule()
    opened = await module.open_eligible_trades(session=session)

    assert opened == 1
    trade = await session.scalar(
        select(PaperTrade).where(PaperTrade.signal_id == signal.id)
    )
    assert trade is not None and trade.status == "open"


async def test_open_eligible_trades_correlation_guard_caps_same_direction(
    session: AsyncSession,
) -> None:
    strategy = _risk_strategy({"max_same_direction_open": 1})
    session.add(strategy)
    await session.commit()
    await _seed_virtual_account(session, balance=1000.0)
    # One YES already open on a different market → the YES side is at cap.
    other = await _seed_bare_market(session, "pm_open_yes")
    await _seed_existing_trade(
        session,
        strategy=strategy,
        market=other,
        direction="YES",
        status="open",
    )
    # Fresh candidate (edge ≥ 0 → YES) on a new market must be blocked.
    _market, signal = await _seed_market_and_signal(
        session, strategy=strategy, edge=0.12
    )
    await session.commit()

    module = PaperTradingModule()
    opened = await module.open_eligible_trades(session=session)

    assert opened == 0
    assert (
        await session.scalar(
            select(PaperTrade).where(PaperTrade.signal_id == signal.id)
        )
        is None
    )


async def test_open_eligible_trades_correlation_guard_is_directional(
    session: AsyncSession,
) -> None:
    # Guard is per-direction, not a blanket halt: a YES book at cap must not
    # block a NO entry (a NO entry actually reduces book correlation).
    strategy = _risk_strategy({"max_same_direction_open": 1})
    session.add(strategy)
    await session.commit()
    await _seed_virtual_account(session, balance=1000.0)
    other = await _seed_bare_market(session, "pm_open_yes")
    await _seed_existing_trade(
        session,
        strategy=strategy,
        market=other,
        direction="YES",
        status="open",
    )
    _market, signal = await _seed_market_and_signal(
        session, strategy=strategy, status="paper_trade_candidate", edge=-0.2
    )
    await session.commit()

    module = PaperTradingModule()
    opened = await module.open_eligible_trades(session=session)

    assert opened == 1
    trade = await session.scalar(
        select(PaperTrade).where(PaperTrade.signal_id == signal.id)
    )
    assert trade is not None
    assert trade.direction == "NO"
