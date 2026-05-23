import asyncio
from collections.abc import Callable
from typing import Any

from sqlalchemy import func, select

from app.db.models import News
from app.db.session import SessionLocal
from app.modules.analytics.service import AnalyticsModule
from app.modules.antipattern.service import AntipatternModule
from app.modules.error_review.service import ErrorReviewModule
from app.modules.llm_analysis.service import LLMAnalysisModule
from app.modules.llm_scorer.service import LLMScorerModule
from app.modules.llm_trader.service import LLMTraderModule
from app.modules.market_data.service import MarketDataModule
from app.modules.news_ingestion.service import NewsIngestionModule
from app.workers.celery_app import celery_app


async def run_market_refresh_job(
    session_factory: Callable[[], Any] = SessionLocal,
    module_factory: Callable[[], Any] = MarketDataModule,
) -> int:
    module = module_factory()
    async with session_factory() as session:
        return await module.sync_markets(session)


def run_market_refresh_job_sync() -> int:
    return asyncio.run(run_market_refresh_job())


async def run_market_snapshot_job(
    session_factory: Callable[[], Any] = SessionLocal,
    module_factory: Callable[[], Any] = MarketDataModule,
) -> int:
    module = module_factory()
    async with session_factory() as session:
        return await module.capture_snapshots(session)


def run_market_snapshot_job_sync() -> int:
    return asyncio.run(run_market_snapshot_job())


async def run_news_ingestion_job(
    session_factory: Callable[[], Any] = SessionLocal,
    module_factory: Callable[[], Any] = NewsIngestionModule,
) -> int:
    module = module_factory()
    async with session_factory() as session:
        return await module.ingest_news(session)


def run_news_ingestion_job_sync() -> int:
    return asyncio.run(run_news_ingestion_job())


async def run_news_analysis_job(
    session_factory: Callable[[], Any] = SessionLocal,
    module_factory: Callable[[], Any] = LLMAnalysisModule,
) -> int:
    module = module_factory()
    async with session_factory() as session:
        return await module.analyze_pending_news(session)


def run_news_analysis_job_sync() -> int:
    return asyncio.run(run_news_analysis_job())


async def count_pending_news(
    session_factory: Callable[[], Any] = SessionLocal,
) -> int:
    async with session_factory() as session:
        return int(
            await session.scalar(
                select(func.count())
                .select_from(News)
                .where(News.processing_status.in_(("new", "queued")))
            )
            or 0
        )


def count_pending_news_sync() -> int:
    return asyncio.run(count_pending_news())


async def run_llm_trader_job(
    session_factory: Callable[[], Any] = SessionLocal,
    module_factory: Callable[[], Any] = LLMTraderModule,
) -> int:
    module = module_factory()
    async with session_factory() as session:
        return await module.run_cycle(session)


def run_llm_trader_job_sync() -> int:
    return asyncio.run(run_llm_trader_job())


async def run_llm_scorer_job(
    session_factory: Callable[[], Any] = SessionLocal,
    module_factory: Callable[[], Any] = LLMScorerModule,
) -> dict[str, int]:
    module = module_factory()
    async with session_factory() as session:
        return await module.run_cycle(session)


def run_llm_scorer_job_sync() -> dict[str, int]:
    return asyncio.run(run_llm_scorer_job())


async def run_auto_review_job(
    session_factory: Callable[[], Any] = SessionLocal,
    review_module_factory: Callable[[], Any] = ErrorReviewModule,
    antipattern_module_factory: Callable[[], Any] = AntipatternModule,
) -> int:
    review_module = review_module_factory()
    antipattern_module = antipattern_module_factory()
    async with session_factory() as session:
        review_count = await review_module.create_auto_reviews(session)
        antipattern_count = await antipattern_module.detect_for_recent_signals(session)
        return review_count + antipattern_count


def run_auto_review_job_sync() -> int:
    return asyncio.run(run_auto_review_job())


async def run_analytics_refresh_job(
    session_factory: Callable[[], Any] = SessionLocal,
    module_factory: Callable[[], Any] = AnalyticsModule,
) -> int:
    module = module_factory()
    async with session_factory() as session:
        return await module.refresh_aggregates(session)


def run_analytics_refresh_job_sync() -> int:
    return asyncio.run(run_analytics_refresh_job())


@celery_app.task
def market_refresh_task() -> str:
    processed = run_market_refresh_job_sync()
    return f"market_refresh_task completed: {processed}"


@celery_app.task
def market_snapshot_task() -> str:
    processed = run_market_snapshot_job_sync()
    return f"market_snapshot_task completed: {processed}"


@celery_app.task
def news_ingestion_task() -> str:
    processed = run_news_ingestion_job_sync()
    return f"news_ingestion_task completed: {processed}"


@celery_app.task
def news_analysis_task() -> str:
    processed = run_news_analysis_job_sync()
    if processed > 0:
        # New analyses make markets "dirty" → run the LLM trader event-driven.
        llm_trader_task.delay()
    # Self-chain: модуль работает батчами по batch_size, а ingestion поднимает
    # сразу всю RSS-простыню. Если очередь не осушена, дёрнем себя ещё раз
    # вместо того чтобы ждать следующего beat-тика.
    if count_pending_news_sync() > 0:
        news_analysis_task.delay()
    return f"news_analysis_task completed: {processed}"


@celery_app.task
def llm_trader_task() -> str:
    processed = run_llm_trader_job_sync()
    return f"llm_trader_task completed: {processed}"


@celery_app.task
def llm_scorer_task() -> str:
    result = run_llm_scorer_job_sync()
    return (
        f"llm_scorer_task completed: prices={result['prices']} "
        f"resolutions={result['resolutions']}"
    )


@celery_app.task
def auto_review_task() -> str:
    processed = run_auto_review_job_sync()
    return f"auto_review_task completed: {processed}"


@celery_app.task
def analytics_refresh_task() -> str:
    processed = run_analytics_refresh_job_sync()
    return f"analytics_refresh_task completed: {processed}"
