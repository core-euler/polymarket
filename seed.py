"""
Bootstrap script for first-run data initialization.

Goals:
1. Always create core defaults (strategy config, sources, virtual account).
2. Execute initial pipeline once to populate real markets/news from external APIs.
3. Purge any leftover demo artifacts from previous bootstrap runs.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models.entities import (
    LLMAnalysis,
    Market,
    News,
    PaperTrade,
    Signal,
    Source,
    StrategyConfig,
    VirtualAccount,
)
from app.db.session import SessionLocal
from app.modules.llm_analysis.service import LLMAnalysisModule
from app.modules.llm_trader.service import LLMTraderModule
from app.modules.market_data.service import MarketDataModule
from app.modules.news_ingestion.service import NewsIngestionModule


DEFAULT_STRATEGY = {
    "profile_name": "default",
    "version": 5,
    # v5 — LLM-as-trader. The signal engine and the paper-trading rule layer
    # are retired (docs/STRATEGY_JOURNAL.md, v5). The trader LLM decides
    # open/close/hold/adjust, side, size and risk directly from analysis +
    # price + portfolio. There are intentionally NO edge thresholds and NO
    # code-level trading rules here — judgment lives in the model + prompt.
    "parameters_json": {},
    "paper_trading_rules_json": {},
    "antipattern_rules_json": {
        "confidence_penalty": 0.15,
        "block_auto_trade_on_match": True,
    },
    "active_flag": True,
}

DEFAULT_SOURCES = [
    {
        "name": "Reuters Top News",
        "source_type": "rss",
        "url": "https://feeds.reuters.com/reuters/topNews",
        "domain": "reuters.com",
        "topic": "general",
        "language": "en",
        "trust_score": 0.92,
        "priority": 10,
        "active_flag": True,
    },
    {
        "name": "AP News",
        "source_type": "rss",
        "url": "https://feeds.apnews.com/rss/apf-topnews",
        "domain": "apnews.com",
        "topic": "general",
        "language": "en",
        "trust_score": 0.92,
        "priority": 10,
        "active_flag": True,
    },
    {
        "name": "BBC News",
        "source_type": "rss",
        "url": "http://feeds.bbci.co.uk/news/rss.xml",
        "domain": "bbc.com",
        "topic": "general",
        "language": "en",
        "trust_score": 0.88,
        "priority": 8,
        "active_flag": True,
    },
    {
        "name": "Politico",
        "source_type": "rss",
        "url": "https://rss.politico.com/politics-news.xml",
        "domain": "politico.com",
        "topic": "politics",
        "language": "en",
        "trust_score": 0.82,
        "priority": 9,
        "active_flag": True,
    },
    {
        "name": "The Hill",
        "source_type": "rss",
        "url": "https://thehill.com/rss/syndicator/19109",
        "domain": "thehill.com",
        "topic": "politics",
        "language": "en",
        "trust_score": 0.75,
        "priority": 7,
        "active_flag": True,
    },
    {
        "name": "CoinDesk",
        "source_type": "rss",
        "url": "https://www.coindesk.com/arc/outboundfeeds/rss/",
        "domain": "coindesk.com",
        "topic": "crypto",
        "language": "en",
        "trust_score": 0.80,
        "priority": 8,
        "active_flag": True,
    },
    {
        "name": "CoinTelegraph",
        "source_type": "rss",
        "url": "https://cointelegraph.com/rss",
        "domain": "cointelegraph.com",
        "topic": "crypto",
        "language": "en",
        "trust_score": 0.72,
        "priority": 7,
        "active_flag": True,
    },
    {
        "name": "Reuters Business",
        "source_type": "rss",
        "url": "https://feeds.reuters.com/reuters/businessNews",
        "domain": "reuters.com",
        "topic": "macro",
        "language": "en",
        "trust_score": 0.92,
        "priority": 9,
        "active_flag": True,
    },
    {
        "name": "Financial Times",
        "source_type": "rss",
        "url": "https://www.ft.com/rss/home",
        "domain": "ft.com",
        "topic": "macro",
        "language": "en",
        "trust_score": 0.88,
        "priority": 8,
        "active_flag": True,
    },
    {
        "name": "ESPN",
        "source_type": "rss",
        "url": "https://www.espn.com/espn/rss/news",
        "domain": "espn.com",
        "topic": "sports",
        "language": "en",
        "trust_score": 0.80,
        "priority": 6,
        "active_flag": True,
    },
]

async def _run_step(
    *,
    name: str,
    session: AsyncSession,
    action: Callable[[], Awaitable[int]],
) -> int:
    try:
        processed = await action()
        print(f"[seed] {name}: {processed}")
        return int(processed)
    except Exception as exc:
        await session.rollback()
        print(f"[seed] {name}: failed ({exc})")
        return 0


async def ensure_core_defaults(session: AsyncSession) -> None:
    now = datetime.now(timezone.utc)
    profile = DEFAULT_STRATEGY["profile_name"]
    target_version = DEFAULT_STRATEGY["version"]
    existing_strategy = await session.scalar(
        select(StrategyConfig).where(
            StrategyConfig.profile_name == profile,
            StrategyConfig.version == target_version,
        )
    )
    if existing_strategy is None:
        session.add(StrategyConfig(created_at=now, **DEFAULT_STRATEGY))
        # Deactivate any older active versions of the same profile so the
        # signal engine consistently picks our new version. Old configs are
        # kept (immutable per DATA_MODEL.md) for audit trails of past signals.
        deactivated = await session.execute(
            update(StrategyConfig)
            .where(
                StrategyConfig.profile_name == profile,
                StrategyConfig.version < target_version,
                StrategyConfig.active_flag.is_(True),
            )
            .values(active_flag=False)
        )
        print(
            f"[seed] StrategyConfig created: {profile} v{target_version} "
            f"(deactivated {deactivated.rowcount} older active version(s))"
        )
    else:
        if not existing_strategy.active_flag:
            existing_strategy.active_flag = True
            print(f"[seed] StrategyConfig activated: {profile} v{target_version}")
        else:
            print(f"[seed] StrategyConfig already exists: {profile} v{target_version}")

    for src in DEFAULT_SOURCES:
        existing_source = await session.scalar(select(Source).where(Source.url == src["url"]))
        if existing_source is None:
            session.add(Source(**src))
            print(f"[seed] Source created: {src['name']}")

    account = await session.scalar(select(VirtualAccount).order_by(VirtualAccount.id.asc()))
    if account is None:
        session.add(VirtualAccount(balance=100.0, initial_balance=100.0))
        print("[seed] VirtualAccount created: $100.00")

    await session.commit()


async def run_initial_pipeline(session: AsyncSession) -> dict[str, int]:
    # Fast, side-effect-free bootstrap steps. LLM analysis, signal generation
    # and paper trades are driven by Celery beat by default. To pre-populate
    # them from seed itself, set SEED_RUN_LLM=true (see drain_llm_pipeline).
    market_module = MarketDataModule()
    news_module = NewsIngestionModule()

    results: dict[str, int] = {}
    results["markets_synced"] = await _run_step(
        name="market_sync",
        session=session,
        action=lambda: market_module.sync_markets(session),
    )
    results["snapshots"] = await _run_step(
        name="market_snapshots",
        session=session,
        action=lambda: market_module.capture_snapshots(session),
    )
    results["news_ingested"] = await _run_step(
        name="news_ingestion",
        session=session,
        action=lambda: news_module.ingest_news(session),
    )
    return results


async def drain_llm_pipeline(
    session: AsyncSession, *, max_iterations: int
) -> dict[str, int]:
    """Bootstrap-time drain: analyze every pending news item, generate signals,
    open and monitor paper trades. Bounded by ``max_iterations`` so a runaway
    feed cannot loop forever.
    """
    llm_module = LLMAnalysisModule()
    trader_module = LLMTraderModule()

    totals = {"analyses": 0, "trades": 0}

    for iteration in range(1, max_iterations + 1):
        analyses = await _run_step(
            name=f"llm_analysis[{iteration}]",
            session=session,
            action=lambda: llm_module.analyze_pending_news(session),
        )
        totals["analyses"] += analyses
        if analyses == 0:
            break

    totals["trades"] = await _run_step(
        name="llm_trader",
        session=session,
        action=lambda: trader_module.run_cycle(session),
    )
    return totals


async def collect_counts(session: AsyncSession) -> dict[str, int]:
    return {
        "markets": int(await session.scalar(select(func.count()).select_from(Market)) or 0),
        "news": int(await session.scalar(select(func.count()).select_from(News)) or 0),
        "analyses": int(await session.scalar(select(func.count()).select_from(LLMAnalysis)) or 0),
        "signals": int(await session.scalar(select(func.count()).select_from(Signal)) or 0),
        "paper_trades": int(await session.scalar(select(func.count()).select_from(PaperTrade)) or 0),
    }


async def seed() -> None:
    settings = get_settings()
    async with SessionLocal() as session:
        await ensure_core_defaults(session)
        await purge_demo_artifacts(session)
        pipeline_results = await run_initial_pipeline(session)
        if settings.seed_run_llm:
            print("[seed] SEED_RUN_LLM=true → draining LLM/signals/trades")
            drain_results = await drain_llm_pipeline(
                session, max_iterations=settings.seed_drain_max_iterations
            )
            pipeline_results.update(drain_results)
        else:
            print("[seed] SEED_RUN_LLM=false → skipping LLM drain (Celery beat will pick it up)")
        counts = await collect_counts(session)
        print(f"[seed] counts_after_pipeline: {counts}")

    print(f"[seed] completed: {pipeline_results}")


async def purge_demo_artifacts(session: AsyncSession) -> None:
    """Remove leftover demo markets/news/analyses/signals/trades from any previous
    bootstrap so the system runs purely on real Polymarket + RSS data.
    """
    from sqlalchemy import delete

    from app.db.models import LLMAnalysis as _LLM, MarketSnapshot as _Snap, Signal as _Sig
    from app.db.models.entities import PaperTrade as _Trade

    demo_markets = list(
        await session.scalars(
            select(Market).where(Market.polymarket_id.like("demo-%"))
        )
    )
    demo_market_ids = [m.id for m in demo_markets]
    if demo_market_ids:
        await session.execute(delete(_Trade).where(_Trade.market_id.in_(demo_market_ids)))
        await session.execute(delete(_Sig).where(_Sig.market_id.in_(demo_market_ids)))
        await session.execute(delete(_LLM).where(_LLM.market_id.in_(demo_market_ids)))
        await session.execute(delete(_Snap).where(_Snap.market_id.in_(demo_market_ids)))
        await session.execute(delete(Market).where(Market.id.in_(demo_market_ids)))

    demo_source = await session.scalar(
        select(Source).where(Source.url == "https://bootstrap.local/demo-feed")
    )
    if demo_source is not None:
        await session.execute(delete(News).where(News.source_id == demo_source.id))
        await session.execute(delete(Source).where(Source.id == demo_source.id))

    await session.commit()
    if demo_market_ids or demo_source is not None:
        print(
            "[seed] purged demo artifacts: "
            f"markets={len(demo_market_ids)} source={'yes' if demo_source else 'no'}"
        )


if __name__ == "__main__":
    asyncio.run(seed())
