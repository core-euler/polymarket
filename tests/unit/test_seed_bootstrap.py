from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import seed
from app.db.base import Base
from app.db.models import StrategyConfig
from app.db.models.entities import VirtualAccount


class _FakeSession:
    def __init__(self) -> None:
        self.rollback_calls = 0

    async def rollback(self) -> None:
        self.rollback_calls += 1


async def test_run_step_rolls_back_on_failure() -> None:
    session = _FakeSession()

    async def _ok() -> int:
        return 5

    async def _fail() -> int:
        raise RuntimeError("boom")

    ok_result = await seed._run_step(name="ok", session=session, action=_ok)
    fail_result = await seed._run_step(name="fail", session=session, action=_fail)

    assert ok_result == 5
    assert fail_result == 0
    assert session.rollback_calls == 1


async def test_run_initial_pipeline_calls_modules_in_order(monkeypatch) -> None:
    calls: list[str] = []
    session = _FakeSession()

    class _Market:
        async def sync_markets(self, current_session) -> int:
            assert current_session is session
            calls.append("market_sync")
            return 1

        async def capture_snapshots(self, current_session) -> int:
            assert current_session is session
            calls.append("market_snapshots")
            return 2

    class _News:
        async def ingest_news(self, current_session) -> int:
            assert current_session is session
            calls.append("news_ingestion")
            return 3

    monkeypatch.setattr(seed, "MarketDataModule", lambda: _Market())
    monkeypatch.setattr(seed, "NewsIngestionModule", lambda: _News())

    results = await seed.run_initial_pipeline(session)

    assert results == {
        "markets_synced": 1,
        "snapshots": 2,
        "news_ingested": 3,
    }
    assert calls == [
        "market_sync",
        "market_snapshots",
        "news_ingestion",
    ]


@pytest.fixture
async def real_session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as db:
        yield db
    await engine.dispose()


async def test_ensure_core_defaults_creates_default_when_db_empty(real_session: AsyncSession) -> None:
    await seed.ensure_core_defaults(real_session)

    rows = list(
        await real_session.scalars(
            select(StrategyConfig).order_by(StrategyConfig.version.asc())
        )
    )
    assert len(rows) == 1
    assert rows[0].version == seed.DEFAULT_STRATEGY["version"]
    assert rows[0].active_flag is True
    # v5 retired the edge/rule params — both config blobs are empty.
    assert rows[0].parameters_json == seed.DEFAULT_STRATEGY["parameters_json"]
    assert rows[0].paper_trading_rules_json == seed.DEFAULT_STRATEGY["paper_trading_rules_json"]


async def test_ensure_core_defaults_deactivates_legacy_v1(real_session: AsyncSession) -> None:
    # Simulate the user's current state: an active v1 with old keys only.
    legacy = StrategyConfig(
        profile_name="default",
        version=1,
        parameters_json={"min_confidence": 0.55, "min_edge": 0.05},
        paper_trading_rules_json={"take_profit_pct": 0.15, "stop_loss_pct": 0.10},
        antipattern_rules_json={},
        active_flag=True,
        created_at=datetime(2026, 3, 13, 10, 0, tzinfo=timezone.utc),
    )
    real_session.add(legacy)
    real_session.add(VirtualAccount(balance=100.0, initial_balance=100.0))
    await real_session.commit()

    await seed.ensure_core_defaults(real_session)

    rows = list(
        await real_session.scalars(
            select(StrategyConfig).order_by(StrategyConfig.version.asc())
        )
    )
    assert [r.version for r in rows] == [1, seed.DEFAULT_STRATEGY["version"]]
    assert rows[0].active_flag is False  # legacy deactivated
    assert rows[1].active_flag is True
    assert rows[1].parameters_json == seed.DEFAULT_STRATEGY["parameters_json"]


async def test_ensure_core_defaults_idempotent_when_default_exists(real_session: AsyncSession) -> None:
    await seed.ensure_core_defaults(real_session)
    await seed.ensure_core_defaults(real_session)

    rows = list(await real_session.scalars(select(StrategyConfig)))
    assert len(rows) == 1
    assert rows[0].version == seed.DEFAULT_STRATEGY["version"]


async def test_run_initial_pipeline_continues_after_failed_step(monkeypatch) -> None:
    calls: list[str] = []
    session = _FakeSession()

    class _Market:
        async def sync_markets(self, _session) -> int:
            calls.append("market_sync")
            return 1

        async def capture_snapshots(self, _session) -> int:
            calls.append("market_snapshots")
            raise RuntimeError("snapshot unavailable")

    class _News:
        async def ingest_news(self, _session) -> int:
            calls.append("news_ingestion")
            return 3

    monkeypatch.setattr(seed, "MarketDataModule", lambda: _Market())
    monkeypatch.setattr(seed, "NewsIngestionModule", lambda: _News())

    results = await seed.run_initial_pipeline(session)

    assert results["markets_synced"] == 1
    assert results["snapshots"] == 0
    assert results["news_ingested"] == 3
    assert session.rollback_calls == 1
    assert calls == [
        "market_sync",
        "market_snapshots",
        "news_ingestion",
    ]
