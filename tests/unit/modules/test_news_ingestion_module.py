from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.models import News, Source
from app.modules.news_ingestion.service import NewsIngestionModule


class FakeSourceFetcher:
    def __init__(self, by_source_url: dict[str, list[dict]]) -> None:
        self.by_source_url = by_source_url

    async def fetch(self, source: Source) -> list[dict]:
        return self.by_source_url.get(source.url, [])


@pytest.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as db_session:
        yield db_session
    await engine.dispose()


async def test_ingest_news_creates_records_for_active_sources(session: AsyncSession) -> None:
    source = Source(
        name="Source A",
        source_type="rss",
        url="https://source-a.test/rss",
        domain="source-a.test",
        topic="politics",
        language="en",
        trust_score=0.8,
        priority=1,
        active_flag=True,
    )
    session.add(source)
    await session.commit()

    fetcher = FakeSourceFetcher(
        {
            "https://source-a.test/rss": [
                {
                    "title": "Election update",
                    "url": "https://source-a.test/election-update",
                    "published_at": "2026-03-13T10:00:00Z",
                    "summary": "Short summary",
                    "content": "Long content",
                }
            ]
        }
    )
    module = NewsIngestionModule(source_fetcher=fetcher)

    processed = await module.ingest_news(session=session)

    assert processed == 1
    news_rows = list(await session.scalars(select(News)))
    assert len(news_rows) == 1
    item = news_rows[0]
    assert item.source_id == source.id
    assert item.url == "https://source-a.test/election-update"
    assert item.title == "Election update"
    assert item.topic == "politics"
    assert item.processing_status == "new"
    assert item.content_hash != ""
    assert item.published_at is not None
    assert item.published_at.replace(tzinfo=timezone.utc) == datetime(
        2026, 3, 13, 10, 0, tzinfo=timezone.utc
    )


async def test_ingest_news_deduplicates_by_url_and_content_hash(session: AsyncSession) -> None:
    source = Source(
        name="Source B",
        source_type="rss",
        url="https://source-b.test/rss",
        domain="source-b.test",
        topic="sports",
        language="en",
        trust_score=0.7,
        priority=1,
        active_flag=True,
    )
    session.add(source)
    await session.commit()

    fetcher = FakeSourceFetcher(
        {
            "https://source-b.test/rss": [
                {
                    "title": "Match update",
                    "url": "https://source-b.test/match-update",
                    "summary": "A summary",
                    "content": "A content payload",
                },
                {
                    "title": "Match update",
                    "url": "https://source-b.test/match-update",
                    "summary": "A summary",
                    "content": "A content payload",
                },
                {
                    "title": "Match update duplicate content",
                    "url": "https://source-b.test/another-url",
                    "summary": "A summary",
                    "content": "A content payload",
                },
            ]
        }
    )
    module = NewsIngestionModule(source_fetcher=fetcher)

    first_processed = await module.ingest_news(session=session)
    second_processed = await module.ingest_news(session=session)

    assert first_processed == 1
    assert second_processed == 0
    rows = list(await session.scalars(select(News)))
    assert len(rows) == 1


async def test_ingest_news_ignores_inactive_sources(session: AsyncSession) -> None:
    active = Source(
        name="Active source",
        source_type="rss",
        url="https://active.test/rss",
        domain="active.test",
        topic="politics",
        language="en",
        trust_score=0.9,
        priority=1,
        active_flag=True,
    )
    inactive = Source(
        name="Inactive source",
        source_type="rss",
        url="https://inactive.test/rss",
        domain="inactive.test",
        topic="politics",
        language="en",
        trust_score=0.4,
        priority=1,
        active_flag=False,
    )
    session.add_all([active, inactive])
    await session.commit()

    fetcher = FakeSourceFetcher(
        {
            "https://active.test/rss": [
                {"title": "Active item", "url": "https://active.test/item-1"},
            ],
            "https://inactive.test/rss": [
                {"title": "Inactive item", "url": "https://inactive.test/item-1"},
            ],
        }
    )
    module = NewsIngestionModule(source_fetcher=fetcher)

    processed = await module.ingest_news(session=session)

    assert processed == 1
    rows = list(await session.scalars(select(News).order_by(News.id)))
    assert len(rows) == 1
    assert rows[0].url == "https://active.test/item-1"

