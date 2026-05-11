from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.models import Market, MarketSnapshot
from app.modules.market_data.service import MarketDataModule


class FakePolymarketClient:
    def __init__(self, payload: list[dict]) -> None:
        self.payload = payload

    async def list_markets(self, params=None) -> list[dict]:
        return self.payload


class FakeSnapshotPolymarketClient:
    def __init__(
        self,
        gamma_payloads: list[dict] | None = None,
        midpoint_by_token: dict[str, dict] | None = None,
        book_by_token: dict[str, dict] | None = None,
        fail_tokens: set[str] | None = None,
    ) -> None:
        self.gamma_payloads = gamma_payloads or []
        self.midpoint_by_token = midpoint_by_token or {}
        self.book_by_token = book_by_token or {}
        self.fail_tokens = fail_tokens or set()

    async def list_markets(self, params=None) -> list[dict]:
        return self.gamma_payloads

    async def get_midpoint(self, token_id: str) -> dict:
        if token_id in self.fail_tokens:
            raise RuntimeError("midpoint failed")
        return self.midpoint_by_token.get(token_id, {"mid": "0"})

    async def get_order_book(self, token_id: str) -> dict:
        if token_id in self.fail_tokens:
            raise RuntimeError("book failed")
        return self.book_by_token.get(token_id, {"bids": [], "asks": []})


@pytest.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as db_session:
        yield db_session
    await engine.dispose()


async def test_sync_markets_creates_new_markets(session: AsyncSession) -> None:
    client = FakePolymarketClient(
        [
            {
                "id": "pm_1",
                "slug": "market-1",
                "question": "Will event A happen?",
                "category": "politics",
                "active": True,
                "endDate": "2030-01-01T00:00:00Z",
            },
            {
                "id": "pm_2",
                "title": "Will event B happen?",
                "topic": "sports",
                "status": "active",
            },
        ]
    )
    module = MarketDataModule(polymarket_client=client)

    processed = await module.sync_markets(session=session)

    assert processed == 2
    rows = list(await session.scalars(select(Market).order_by(Market.polymarket_id)))
    assert len(rows) == 2
    assert rows[0].polymarket_id == "pm_1"
    assert rows[0].slug == "market-1"
    assert rows[0].question == "Will event A happen?"
    assert rows[0].topic == "politics"
    assert rows[0].status == "active"
    assert rows[0].expires_at is not None
    assert rows[0].expires_at.replace(tzinfo=timezone.utc) == datetime(
        2030, 1, 1, 0, 0, tzinfo=timezone.utc
    )


async def test_sync_markets_updates_existing_market_without_overwriting_flags(
    session: AsyncSession,
) -> None:
    existing = Market(
        polymarket_id="pm_100",
        slug="old-slug",
        title="Old title",
        question="Old question",
        topic="old-topic",
        status="active",
        watchlist_flag=True,
        blacklist_flag=False,
        archived_flag=False,
    )
    session.add(existing)
    await session.commit()

    client = FakePolymarketClient(
        [
            {
                "id": "pm_100",
                "slug": "new-slug",
                "question": "New question",
                "topic": "new-topic",
                "closed": True,
            }
        ]
    )
    module = MarketDataModule(polymarket_client=client)

    processed = await module.sync_markets(session=session)

    assert processed == 1
    refreshed = await session.scalar(select(Market).where(Market.polymarket_id == "pm_100"))
    assert refreshed is not None
    assert refreshed.slug == "new-slug"
    assert refreshed.question == "New question"
    assert refreshed.title == "New question"
    assert refreshed.topic == "new-topic"
    assert refreshed.status == "closed"
    assert refreshed.watchlist_flag is True


async def test_sync_markets_extracts_clob_token_ids(session: AsyncSession) -> None:
    client = FakePolymarketClient(
        [
            {
                "id": "pm_tokens",
                "question": "Q?",
                "clobTokenIds": "[\"tok_yes\", \"tok_no\"]",
            },
            {
                "id": "pm_tokens_native",
                "question": "Q2?",
                "clobTokenIds": ["tok_yes_2", "tok_no_2"],
            },
            {
                "id": "pm_no_tokens",
                "question": "Q3?",
            },
        ]
    )
    module = MarketDataModule(polymarket_client=client)

    await module.sync_markets(session=session)

    rows = {row.polymarket_id: row for row in await session.scalars(select(Market))}
    assert rows["pm_tokens"].yes_token_id == "tok_yes"
    assert rows["pm_tokens"].no_token_id == "tok_no"
    assert rows["pm_tokens_native"].yes_token_id == "tok_yes_2"
    assert rows["pm_tokens_native"].no_token_id == "tok_no_2"
    assert rows["pm_no_tokens"].yes_token_id is None
    assert rows["pm_no_tokens"].no_token_id is None


async def test_sync_markets_skips_records_without_identifier(session: AsyncSession) -> None:
    client = FakePolymarketClient(
        [
            {"slug": "missing-id", "question": "No id here"},
            {"id": "pm_valid", "question": "Valid market"},
        ]
    )
    module = MarketDataModule(polymarket_client=client)

    processed = await module.sync_markets(session=session)

    assert processed == 1
    rows = list(await session.scalars(select(Market)))
    assert len(rows) == 1
    assert rows[0].polymarket_id == "pm_valid"


async def test_capture_snapshots_creates_snapshot_for_active_markets(session: AsyncSession) -> None:
    market = Market(
        polymarket_id="pm_active",
        slug="active-market",
        title="Active market",
        question="Will active market move?",
        topic="politics",
        status="active",
        watchlist_flag=True,
        blacklist_flag=False,
        archived_flag=False,
        yes_token_id="tok_yes",
    )
    session.add(market)
    await session.commit()

    client = FakeSnapshotPolymarketClient(
        gamma_payloads=[
            {
                "id": "pm_active",
                "outcomePrices": "[\"0.55\", \"0.45\"]",
                "liquidityNum": 1234.5,
                "volume24hr": 9876.0,
                "bestBid": "0.54",
                "bestAsk": "0.56",
            }
        ],
        midpoint_by_token={"tok_yes": {"mid": "0.57"}},
        book_by_token={
            "tok_yes": {
                "bids": [{"price": "0.55"}],
                "asks": [{"price": "0.60"}],
            }
        },
    )
    module = MarketDataModule(polymarket_client=client)

    processed = await module.capture_snapshots(session=session)

    assert processed == 1
    snapshots = list(await session.scalars(select(MarketSnapshot)))
    assert len(snapshots) == 1
    snapshot = snapshots[0]
    assert snapshot.market_id == market.id
    # CLOB midpoint overrides Gamma price when yes_token_id is set
    assert snapshot.last_price == 0.57
    assert snapshot.implied_probability == 0.57
    assert snapshot.liquidity == 1234.5
    assert snapshot.volume == 9876.0
    # spread comes from CLOB book bids/asks
    assert round(snapshot.spread, 6) == 0.05
    assert snapshot.raw_payload["gamma"]["id"] == "pm_active"
    assert snapshot.raw_payload["clob"]["midpoint"]["mid"] == "0.57"


async def test_capture_snapshots_uses_gamma_only_when_no_token_id(session: AsyncSession) -> None:
    market = Market(
        polymarket_id="pm_no_token",
        slug="no-token",
        title="No token market",
        question="Q?",
        topic="politics",
        status="active",
        watchlist_flag=False,
        blacklist_flag=False,
        archived_flag=False,
    )
    session.add(market)
    await session.commit()

    client = FakeSnapshotPolymarketClient(
        gamma_payloads=[
            {
                "id": "pm_no_token",
                "outcomePrices": "[\"0.42\", \"0.58\"]",
                "liquidityNum": 100.0,
                "volume24hr": 200.0,
                "spread": "0.03",
            }
        ],
    )
    module = MarketDataModule(polymarket_client=client)

    processed = await module.capture_snapshots(session=session)

    assert processed == 1
    snapshot = (await session.scalars(select(MarketSnapshot))).one()
    assert snapshot.last_price == 0.42
    assert snapshot.liquidity == 100.0
    assert snapshot.volume == 200.0
    assert snapshot.spread == 0.03
    assert snapshot.raw_payload["clob"] == {}


async def test_capture_snapshots_skips_markets_missing_from_gamma(session: AsyncSession) -> None:
    market = Market(
        polymarket_id="demo-only",
        slug="demo",
        title="Demo",
        question="Demo?",
        topic="general",
        status="active",
    )
    session.add(market)
    await session.commit()

    client = FakeSnapshotPolymarketClient(gamma_payloads=[])
    module = MarketDataModule(polymarket_client=client)

    processed = await module.capture_snapshots(session=session)
    assert processed == 0
    assert list(await session.scalars(select(MarketSnapshot))) == []


async def test_capture_snapshots_filters_non_eligible_markets(session: AsyncSession) -> None:
    active_market = Market(
        polymarket_id="pm_active_2",
        slug="active-market-2",
        title="Active market 2",
        question="Will active market 2 move?",
        topic="sports",
        status="active",
        watchlist_flag=False,
        blacklist_flag=False,
        archived_flag=False,
    )
    inactive_market = Market(
        polymarket_id="pm_inactive",
        slug="inactive-market",
        title="Inactive market",
        question="Will inactive market move?",
        topic="sports",
        status="closed",
        watchlist_flag=False,
        blacklist_flag=False,
        archived_flag=False,
    )
    blacklisted_market = Market(
        polymarket_id="pm_blacklisted",
        slug="blacklisted-market",
        title="Blacklisted market",
        question="Will blacklisted market move?",
        topic="sports",
        status="active",
        watchlist_flag=False,
        blacklist_flag=True,
        archived_flag=False,
    )
    archived_market = Market(
        polymarket_id="pm_archived",
        slug="archived-market",
        title="Archived market",
        question="Will archived market move?",
        topic="sports",
        status="active",
        watchlist_flag=False,
        blacklist_flag=False,
        archived_flag=True,
    )
    session.add_all([active_market, inactive_market, blacklisted_market, archived_market])
    await session.commit()

    client = FakeSnapshotPolymarketClient(
        gamma_payloads=[
            {
                "id": "pm_active_2",
                "outcomePrices": "[\"0.49\", \"0.51\"]",
                "liquidityNum": 42.0,
                "volume24hr": 12.0,
            },
            {"id": "pm_inactive", "outcomePrices": "[\"0.5\", \"0.5\"]"},
            {"id": "pm_blacklisted", "outcomePrices": "[\"0.5\", \"0.5\"]"},
            {"id": "pm_archived", "outcomePrices": "[\"0.5\", \"0.5\"]"},
        ]
    )
    module = MarketDataModule(polymarket_client=client)

    processed = await module.capture_snapshots(session=session)

    assert processed == 1
    snapshots = list(await session.scalars(select(MarketSnapshot)))
    assert len(snapshots) == 1
    assert snapshots[0].market_id == active_market.id


async def test_capture_snapshots_rejects_extreme_price_with_dead_clob(session: AsyncSession) -> None:
    # Bug regression: long-dated illiquid markets get gamma outcomePrices like
    # ["1.0", "0.0"] from one stale trade, with no live CLOB book to override.
    # Persisting that lets paper trades close at fake +1.00 mark. Reject.
    market = Market(
        polymarket_id="pm_extreme",
        slug="ceasefire",
        title="Russia x Ukraine ceasefire by June 30, 2026",
        question="Will ceasefire happen by 2026-06-30?",
        topic="politics",
        status="active",
        yes_token_id="tok_dead",
    )
    session.add(market)
    await session.commit()

    client = FakeSnapshotPolymarketClient(
        gamma_payloads=[
            {
                "id": "pm_extreme",
                "outcomePrices": "[\"1.0\", \"0.0\"]",  # stale extreme
                "liquidityNum": 1.0,
                "volume24hr": 0.0,
            }
        ],
        midpoint_by_token={"tok_dead": {"mid": "0"}},  # no live midpoint
        book_by_token={"tok_dead": {"bids": [], "asks": []}},
    )
    module = MarketDataModule(polymarket_client=client)

    processed = await module.capture_snapshots(session=session)

    assert processed == 0
    assert list(await session.scalars(select(MarketSnapshot))) == []


async def test_capture_snapshots_keeps_extreme_price_when_clob_confirms(session: AsyncSession) -> None:
    # If CLOB midpoint actually agrees that price is extreme, that is a real
    # quote (rare, but possible at resolution boundary) — keep the snapshot.
    market = Market(
        polymarket_id="pm_resolved_high",
        slug="resolved",
        title="Almost-resolved",
        question="Q?",
        topic="politics",
        status="active",
        yes_token_id="tok_live",
    )
    session.add(market)
    await session.commit()

    client = FakeSnapshotPolymarketClient(
        gamma_payloads=[
            {
                "id": "pm_resolved_high",
                "outcomePrices": "[\"0.99\", \"0.01\"]",
                "liquidityNum": 1000.0,
                "volume24hr": 500.0,
            }
        ],
        midpoint_by_token={"tok_live": {"mid": "0.99"}},
        book_by_token={"tok_live": {"bids": [{"price": "0.985"}], "asks": [{"price": "0.995"}]}},
    )
    module = MarketDataModule(polymarket_client=client)

    processed = await module.capture_snapshots(session=session)

    assert processed == 1
    snapshot = (await session.scalars(select(MarketSnapshot))).one()
    assert snapshot.last_price == 0.99


async def test_capture_snapshots_falls_back_to_gamma_on_clob_failure(session: AsyncSession) -> None:
    market = Market(
        polymarket_id="pm_clob_fail",
        slug="m",
        title="m",
        question="m?",
        topic="politics",
        status="active",
        yes_token_id="tok_fail",
    )
    session.add(market)
    await session.commit()

    client = FakeSnapshotPolymarketClient(
        gamma_payloads=[
            {
                "id": "pm_clob_fail",
                "outcomePrices": "[\"0.61\", \"0.39\"]",
                "liquidityNum": 100.0,
                "volume24hr": 50.0,
            }
        ],
        fail_tokens={"tok_fail"},
    )
    module = MarketDataModule(polymarket_client=client)

    processed = await module.capture_snapshots(session=session)

    assert processed == 1
    snapshot = (await session.scalars(select(MarketSnapshot))).one()
    # CLOB failed → price falls back to Gamma outcomePrices YES
    assert snapshot.last_price == 0.61
