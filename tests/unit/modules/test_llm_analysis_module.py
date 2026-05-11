from datetime import datetime, timezone

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.models import LLMAnalysis, Market, News, Source
from app.modules.llm_analysis.relevance_checker import NullRelevanceChecker, RelevanceResult
from app.modules.llm_analysis.service import CometAnalyzerAdapter, LLMAnalysisModule


class FakeLLMAnalyzer:
    model_name = "fake-llm"

    async def analyze(self, *, news: News, market: Market) -> dict:
        _ = news
        _ = market
        return {
            "relevance": "relevant",
            "impact_direction": "yes",
            "impact_strength": 0.5,
            "confidence": 0.8,
            "summary": "Structured summary",
            "facts": {"k": "v"},
            "entities": {"people": ["a"]},
            "uncertainties": {"items": []},
            "contradictions": {"items": []},
        }


class StubRelevanceChecker:
    def __init__(self, result: RelevanceResult = RelevanceResult(relevant=True, score=1.0)) -> None:
        self.result = result
        self.calls = 0

    async def check(self, *, news: News, market: Market) -> RelevanceResult:
        _ = news
        _ = market
        self.calls += 1
        return self.result


class FakeCometClient:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.model = "fake-comet-model"

    async def analyze_text(self, prompt: str) -> dict:
        _ = prompt
        return self.payload


@pytest.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as db_session:
        yield db_session
    await engine.dispose()


async def test_analyze_pending_news_creates_analysis_and_updates_news(session: AsyncSession) -> None:
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
        polymarket_id="pm_llm",
        slug="llm-market",
        title="Election market",
        question="Will candidate Smith win the election?",
        topic="politics",
        status="active",
        watchlist_flag=False,
        blacklist_flag=False,
        archived_flag=False,
    )
    news = News(
        source_id=1,
        title="Smith leads in election polls",
        url="https://source.test/news-1",
        published_at=datetime(2026, 3, 13, 10, 0, tzinfo=timezone.utc),
        discovered_at=datetime(2026, 3, 13, 10, 1, tzinfo=timezone.utc),
        summary_text="Smith candidate election update",
        raw_content="Polls show candidate Smith ahead in the election",
        language="en",
        content_hash="hash-llm-1",
        topic="politics",
        processing_status="new",
        created_at=datetime(2026, 3, 13, 10, 1, tzinfo=timezone.utc),
    )
    session.add_all([source, market])
    await session.flush()
    news.source_id = source.id
    session.add(news)
    await session.commit()

    module = LLMAnalysisModule(
        analyzer=FakeLLMAnalyzer(), relevance_checker=NullRelevanceChecker()
    )
    processed = await module.analyze_pending_news(session=session)

    assert processed == 1
    analyses_count = await session.scalar(select(func.count()).select_from(LLMAnalysis))
    assert analyses_count == 1
    refreshed_news = await session.scalar(select(News).where(News.id == news.id))
    assert refreshed_news is not None
    assert refreshed_news.processing_status == "analyzed"


async def test_analyze_pending_news_is_idempotent(session: AsyncSession) -> None:
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
        polymarket_id="pm_llm2",
        slug="llm-market-2",
        title="Election market 2",
        question="Will candidate Smith win the election?",
        topic="politics",
        status="active",
        watchlist_flag=False,
        blacklist_flag=False,
        archived_flag=False,
    )
    news = News(
        source_id=1,
        title="Smith leads election polls again",
        url="https://source.test/news-2",
        published_at=datetime(2026, 3, 13, 10, 0, tzinfo=timezone.utc),
        discovered_at=datetime(2026, 3, 13, 10, 1, tzinfo=timezone.utc),
        summary_text="Election polls Smith candidate",
        raw_content="Polls show candidate Smith ahead in the election",
        language="en",
        content_hash="hash-llm-2",
        topic="politics",
        processing_status="new",
        created_at=datetime(2026, 3, 13, 10, 1, tzinfo=timezone.utc),
    )
    session.add_all([source, market])
    await session.flush()
    news.source_id = source.id
    session.add(news)
    await session.commit()

    module = LLMAnalysisModule(
        analyzer=FakeLLMAnalyzer(), relevance_checker=NullRelevanceChecker()
    )
    first = await module.analyze_pending_news(session=session)
    # second run requires news back to "new"; analyze_pending_news flips to "analyzed"
    refreshed = await session.scalar(select(News).where(News.id == news.id))
    refreshed.processing_status = "new"
    await session.commit()
    second = await module.analyze_pending_news(session=session)

    assert first == 1
    assert second == 0
    analyses_count = await session.scalar(select(func.count()).select_from(LLMAnalysis))
    assert analyses_count == 1


async def test_news_ignored_when_no_keyword_overlap(session: AsyncSession) -> None:
    source = Source(
        name="S", source_type="rss", url="https://s/r", domain="s",
        topic="", language="en", trust_score=1.0, priority=1, active_flag=True,
    )
    market = Market(
        polymarket_id="pm_x", slug="x", title="Sports market",
        question="Will the Lakers win?", topic="", status="active",
    )
    news = News(
        source_id=1, title="Inflation hits new record",
        url="https://s/r/1",
        published_at=datetime(2026, 3, 13, tzinfo=timezone.utc),
        discovered_at=datetime(2026, 3, 13, tzinfo=timezone.utc),
        summary_text="Inflation rises",
        raw_content="Macroeconomic inflation report",
        language="en", content_hash="hh", topic="", processing_status="new",
        created_at=datetime(2026, 3, 13, tzinfo=timezone.utc),
    )
    session.add_all([source, market])
    await session.flush()
    news.source_id = source.id
    session.add(news)
    await session.commit()

    fake_relevance = StubRelevanceChecker()
    fake_analyzer = FakeLLMAnalyzer()
    module = LLMAnalysisModule(
        analyzer=fake_analyzer, relevance_checker=fake_relevance
    )
    processed = await module.analyze_pending_news(session=session)

    assert processed == 0
    assert fake_relevance.calls == 0  # never reached Stage-1
    refreshed = await session.scalar(select(News).where(News.id == news.id))
    assert refreshed.processing_status == "ignored"


async def test_batch_size_caps_news_processed_per_run(session: AsyncSession) -> None:
    source = Source(
        name="S", source_type="rss", url="https://s/r", domain="s",
        topic="", language="en", trust_score=1.0, priority=1, active_flag=True,
    )
    market = Market(
        polymarket_id="pm_b", slug="b", title="Election market",
        question="Will candidate Smith win the election?",
        topic="", status="active",
    )
    session.add_all([source, market])
    await session.flush()

    for i in range(5):
        session.add(
            News(
                source_id=source.id,
                title=f"Smith election update {i}",
                url=f"https://s/r/n{i}",
                published_at=datetime(2026, 3, 13, tzinfo=timezone.utc),
                discovered_at=datetime(2026, 3, 13, tzinfo=timezone.utc),
                summary_text="Smith candidate election",
                raw_content="Polls show Smith ahead in election",
                language="en", content_hash=f"h{i}", topic="",
                processing_status="new",
                created_at=datetime(2026, 3, 13, tzinfo=timezone.utc),
            )
        )
    await session.commit()

    module = LLMAnalysisModule(
        analyzer=FakeLLMAnalyzer(),
        relevance_checker=NullRelevanceChecker(),
        batch_size=2,
    )
    processed = await module.analyze_pending_news(session=session)
    assert processed == 2
    pending = await session.scalar(
        select(func.count()).select_from(News).where(News.processing_status == "new")
    )
    assert pending == 3


async def test_stage1_below_threshold_marks_ignored(session: AsyncSession) -> None:
    source = Source(
        name="S", source_type="rss", url="https://s/r", domain="s",
        topic="", language="en", trust_score=1.0, priority=1, active_flag=True,
    )
    market = Market(
        polymarket_id="pm_t", slug="t", title="Election market",
        question="Will candidate Smith win the election?",
        topic="", status="active",
    )
    news = News(
        source_id=1, title="Smith election polls update",
        url="https://s/r/t",
        published_at=datetime(2026, 3, 13, tzinfo=timezone.utc),
        discovered_at=datetime(2026, 3, 13, tzinfo=timezone.utc),
        summary_text="Smith candidate election",
        raw_content="Smith leads in election polls",
        language="en", content_hash="ht", topic="", processing_status="new",
        created_at=datetime(2026, 3, 13, tzinfo=timezone.utc),
    )
    session.add_all([source, market])
    await session.flush()
    news.source_id = source.id
    session.add(news)
    await session.commit()

    not_relevant = StubRelevanceChecker(
        result=__import__(
            "app.modules.llm_analysis.relevance_checker", fromlist=["RelevanceResult"]
        ).RelevanceResult(relevant=False, score=0.1)
    )
    module = LLMAnalysisModule(
        analyzer=FakeLLMAnalyzer(), relevance_checker=not_relevant
    )
    processed = await module.analyze_pending_news(session=session)

    assert processed == 0
    assert not_relevant.calls == 1
    refreshed = await session.scalar(select(News).where(News.id == news.id))
    assert refreshed.processing_status == "ignored"


async def test_comet_adapter_parses_plain_json_response() -> None:
    client = FakeCometClient(
        {
            "choices": [
                {
                    "message": {
                        "content": (
                            '{"relevance":"relevant","impact_direction":"yes","impact_strength":0.7,'
                            '"confidence":0.9,"summary":"Parsed","facts":{"a":1}}'
                        )
                    }
                }
            ]
        }
    )
    adapter = CometAnalyzerAdapter(client=client)

    result = await adapter.analyze(news=News(title="n", raw_content="c"), market=Market(question="q"))

    assert result["relevance"] == "relevant"
    assert result["impact_direction"] == "yes"
    assert result["impact_strength"] == 0.7
    assert result["confidence"] == 0.9
    assert result["summary"] == "Parsed"
    assert result["facts"] == {"a": 1}


async def test_comet_adapter_parses_fenced_json_response() -> None:
    client = FakeCometClient(
        {
            "choices": [
                {
                    "message": {
                        "content": (
                            "```json\n"
                            '{"relevance":"relevant","impact_direction":"no","impact_strength":0.4,'
                            '"confidence":0.6,"summary":"Fence"}'
                            "\n```"
                        )
                    }
                }
            ]
        }
    )
    adapter = CometAnalyzerAdapter(client=client)

    result = await adapter.analyze(news=News(title="n", raw_content="c"), market=Market(question="q"))

    assert result["impact_direction"] == "no"
    assert result["summary"] == "Fence"
