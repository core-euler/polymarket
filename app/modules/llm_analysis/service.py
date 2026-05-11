from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime, timezone
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import LLMAnalysis, Market, News
from app.modules.llm_analysis.comet_client import CometAPIClient
from app.modules.llm_analysis.keyword_filter import CandidateMatch, KeywordFilter
from app.modules.llm_analysis.relevance_checker import (
    CometRelevanceChecker,
    NullRelevanceChecker,
    RelevanceResult,
)


_log = structlog.get_logger("llm_analysis")


class NullAnalyzer:
    model_name = "null-analyzer"

    async def analyze(self, *, news: News, market: Market) -> dict[str, Any]:
        _ = news
        _ = market
        return {
            "relevance": "unknown",
            "impact_direction": "neutral",
            "impact_strength": 0.0,
            "confidence": 0.0,
            "summary": "No-op analyzer result",
            "facts": {},
            "entities": {},
            "uncertainties": {},
            "contradictions": {},
        }


class CometAnalyzerAdapter:
    def __init__(self, client: Any | None = None) -> None:
        self.client = client or CometAPIClient()
        self.model_name = self.client.model or "comet-default"

    async def analyze(self, *, news: News, market: Market) -> dict[str, Any]:
        prompt = (
            "You evaluate whether a news item moves the YES outcome of a "
            "Polymarket prediction market.\n"
            "Return STRICT JSON with these exact keys and value rules:\n"
            "  relevance: \"relevant\" | \"irrelevant\"\n"
            "  impact_direction: \"yes\" | \"no\" | \"neutral\" "
            "(use exactly one of these three; \"yes\" means the news raises "
            "the probability of YES, \"no\" means it lowers it, \"neutral\" "
            "for no material directional effect)\n"
            "  impact_strength: number in [0, 1] (0 = no movement, "
            "1 = very strong movement)\n"
            "  confidence: number in [0, 1]\n"
            "  summary: short string\n"
            "  facts, entities, uncertainties, contradictions: objects\n"
            "Reply with JSON only, no prose, no markdown fences.\n\n"
            f"Market question: {market.question}\n"
            f"News title: {news.title}\n"
            f"News content: {news.raw_content}\n"
        )
        raw = await self.client.analyze_text(prompt=prompt)
        parsed = self._parse_structured_output(raw)
        parsed["trace"] = {"provider": "comet", "raw": raw}
        return parsed

    @classmethod
    def _parse_structured_output(cls, raw: dict[str, Any]) -> dict[str, Any]:
        defaults = {
            "relevance": "unknown",
            "impact_direction": "neutral",
            "impact_strength": 0.0,
            "confidence": 0.0,
            "summary": "",
            "facts": {},
            "entities": {},
            "uncertainties": {},
            "contradictions": {},
        }
        content = cls._extract_content_text(raw)
        payload = cls._parse_json_payload(content)
        if payload is None:
            return defaults

        merged: dict[str, Any] = {**defaults, **payload}
        merged["impact_strength"] = cls._clamp_unit(merged.get("impact_strength"))
        merged["confidence"] = cls._clamp_unit(merged.get("confidence"))
        return merged

    @staticmethod
    def _to_float(value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    @classmethod
    def _clamp_unit(cls, value: Any) -> float:
        # LLM occasionally returns out-of-range numbers (e.g. confidence=5.0).
        # Coerce to a bounded probability instead of letting bad data flow downstream.
        return max(0.0, min(1.0, cls._to_float(value)))

    @staticmethod
    def _extract_content_text(raw: dict[str, Any]) -> str:
        choices = raw.get("choices")
        if not isinstance(choices, list) or not choices:
            return ""
        first = choices[0]
        if not isinstance(first, dict):
            return ""
        message = first.get("message")
        if not isinstance(message, dict):
            return ""
        content = message.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            chunks: list[str] = []
            for part in content:
                if isinstance(part, dict):
                    text = part.get("text")
                    if isinstance(text, str):
                        chunks.append(text)
            return "\n".join(chunks)
        return ""

    @classmethod
    def _parse_json_payload(cls, content: str) -> dict[str, Any] | None:
        text = content.strip()
        if not text:
            return None

        parsed = cls._try_json_load(text)
        if parsed is not None:
            return parsed

        fenced = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        fenced = re.sub(r"\s*```$", "", fenced)
        parsed = cls._try_json_load(fenced.strip())
        if parsed is not None:
            return parsed

        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            parsed = cls._try_json_load(text[start : end + 1])
            if parsed is not None:
                return parsed
        return None

    @staticmethod
    def _try_json_load(value: str) -> dict[str, Any] | None:
        try:
            payload = json.loads(value)
        except json.JSONDecodeError:
            return None
        if isinstance(payload, dict):
            return payload
        return None


class LLMAnalysisModule:
    """Pipeline orchestrator: Stage-0 keyword filter → Stage-1 relevance → Stage-2 deep analysis.

    Hard guardrails: batch cap per run, bounded parallelism, idempotency on
    (news_id, market_id, model_name). News with zero candidate markets are marked
    ``ignored`` so they stop being scanned every tick.
    """

    def __init__(
        self,
        *,
        analyzer: Any | None = None,
        relevance_checker: Any | None = None,
        keyword_filter: KeywordFilter | None = None,
        batch_size: int = 20,
        max_concurrency: int = 5,
        relevance_threshold: float = 0.5,
    ) -> None:
        if analyzer is not None:
            self.analyzer = analyzer
        else:
            from app.core.config import get_settings
            self.analyzer = CometAnalyzerAdapter() if get_settings().comet_api_key else NullAnalyzer()

        if relevance_checker is not None:
            self.relevance_checker = relevance_checker
        else:
            from app.core.config import get_settings
            self.relevance_checker = (
                CometRelevanceChecker() if get_settings().comet_api_key else NullRelevanceChecker()
            )

        self.keyword_filter = keyword_filter or KeywordFilter()
        self.batch_size = max(1, batch_size)
        self.max_concurrency = max(1, max_concurrency)
        self.relevance_threshold = max(0.0, min(1.0, relevance_threshold))

    async def analyze_pending_news(self, session: AsyncSession) -> int:
        pending_items = list(
            await session.scalars(
                select(News)
                .where(News.processing_status.in_(("new", "queued")))
                .order_by(News.id.asc())
                .limit(self.batch_size)
            )
        )
        if not pending_items:
            _log.info("analyze_pending_news.batch_empty")
            return 0

        markets = list(
            await session.scalars(
                select(Market).where(
                    Market.status == "active",
                    Market.blacklist_flag.is_(False),
                    Market.archived_flag.is_(False),
                )
            )
        )
        _log.info(
            "analyze_pending_news.batch_start",
            news_in_batch=len(pending_items),
            active_markets=len(markets),
            batch_size=self.batch_size,
        )
        if not markets:
            for news in pending_items:
                news.processing_status = "ignored"
            await session.commit()
            return 0

        model_name = getattr(self.analyzer, "model_name", "llm-analyzer")
        semaphore = asyncio.Semaphore(self.max_concurrency)
        now = datetime.now(timezone.utc)
        processed = 0

        for news in pending_items:
            candidates = self.keyword_filter.rank_candidates(news=news, markets=markets)
            _log.info(
                "stage0.result",
                news_id=news.id,
                title=(news.title or "")[:80],
                candidate_count=len(candidates),
                top_score=candidates[0].score if candidates else 0.0,
                top_market_id=candidates[0].market.id if candidates else None,
            )
            if not candidates:
                news.processing_status = "ignored"
                continue

            relevance_results = await asyncio.gather(
                *(self._check_relevance(semaphore, news, c) for c in candidates),
                return_exceptions=True,
            )

            survivors: list[CandidateMatch] = []
            for candidate, outcome in zip(candidates, relevance_results, strict=True):
                if isinstance(outcome, Exception):
                    _log.warning(
                        "stage1.error",
                        news_id=news.id,
                        market_id=candidate.market.id,
                        error=str(outcome),
                    )
                    continue
                _log.info(
                    "stage1.result",
                    news_id=news.id,
                    market_id=candidate.market.id,
                    relevant=outcome.relevant,
                    score=outcome.score,
                    threshold=self.relevance_threshold,
                    kept=outcome.relevant and outcome.score >= self.relevance_threshold,
                )
                if outcome.relevant and outcome.score >= self.relevance_threshold:
                    survivors.append(candidate)

            if not survivors:
                news.processing_status = "ignored"
                continue

            survivors = await self._drop_existing_pairs(
                session=session, news=news, candidates=survivors, model_name=model_name
            )
            if not survivors:
                news.processing_status = "analyzed"
                continue

            deep_results = await asyncio.gather(
                *(self._deep_analyze(semaphore, news, c) for c in survivors),
                return_exceptions=True,
            )

            created_for_news = 0
            for candidate, outcome in zip(survivors, deep_results, strict=True):
                if isinstance(outcome, Exception) or not isinstance(outcome, dict):
                    _log.warning(
                        "stage2.error",
                        news_id=news.id,
                        market_id=candidate.market.id,
                        error=str(outcome) if isinstance(outcome, Exception) else "non-dict",
                    )
                    continue
                _log.info(
                    "stage2.persist",
                    news_id=news.id,
                    market_id=candidate.market.id,
                    impact_direction=outcome.get("impact_direction"),
                    impact_strength=outcome.get("impact_strength"),
                    confidence=outcome.get("confidence"),
                )
                session.add(
                    self._build_analysis(
                        news=news,
                        market=candidate.market,
                        result=outcome,
                        model_name=model_name,
                        now=now,
                    )
                )
                processed += 1
                created_for_news += 1

            news.processing_status = "analyzed" if created_for_news > 0 else "failed"

        await session.commit()
        _log.info("analyze_pending_news.batch_done", analyses_created=processed)
        return processed

    async def _check_relevance(
        self, semaphore: asyncio.Semaphore, news: News, candidate: CandidateMatch
    ) -> RelevanceResult:
        async with semaphore:
            return await self.relevance_checker.check(news=news, market=candidate.market)

    async def _deep_analyze(
        self, semaphore: asyncio.Semaphore, news: News, candidate: CandidateMatch
    ) -> dict[str, Any]:
        async with semaphore:
            return await self.analyzer.analyze(news=news, market=candidate.market)

    async def _drop_existing_pairs(
        self,
        *,
        session: AsyncSession,
        news: News,
        candidates: list[CandidateMatch],
        model_name: str,
    ) -> list[CandidateMatch]:
        if not candidates:
            return candidates
        market_ids = [c.market.id for c in candidates]
        existing = set(
            await session.scalars(
                select(LLMAnalysis.market_id).where(
                    LLMAnalysis.news_id == news.id,
                    LLMAnalysis.market_id.in_(market_ids),
                    LLMAnalysis.model_name == model_name,
                )
            )
        )
        return [c for c in candidates if c.market.id not in existing]

    def _build_analysis(
        self,
        *,
        news: News,
        market: Market,
        result: dict[str, Any],
        model_name: str,
        now: datetime,
    ) -> LLMAnalysis:
        return LLMAnalysis(
            news_id=news.id,
            market_id=market.id,
            model_name=model_name,
            prompt_template_version="v1",
            relevance=str(result.get("relevance", "unknown")),
            event_time=self._parse_datetime(result.get("event_time")),
            impact_direction=str(result.get("impact_direction", "neutral")),
            impact_strength=float(result.get("impact_strength", 0.0) or 0.0),
            confidence=float(result.get("confidence", 0.0) or 0.0),
            facts_json=result.get("facts", {}) or {},
            entities_json=result.get("entities", {}) or {},
            uncertainties_json=result.get("uncertainties", {}) or {},
            contradictions_json=result.get("contradictions", {}) or {},
            summary=str(result.get("summary", "")),
            trace_json=result.get("trace", {}) or {},
            created_at=now,
        )

    @staticmethod
    def _parse_datetime(value: Any) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            if value.tzinfo is None:
                return value.replace(tzinfo=timezone.utc)
            return value
        if isinstance(value, str):
            raw = value.strip()
            if not raw:
                return None
            if raw.endswith("Z"):
                raw = raw[:-1] + "+00:00"
            try:
                parsed = datetime.fromisoformat(raw)
            except ValueError:
                return None
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=timezone.utc)
            return parsed
        return None
