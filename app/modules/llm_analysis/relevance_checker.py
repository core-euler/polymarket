from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from app.db.models import Market, News
from app.modules.llm_analysis.comet_client import CometAPIClient


@dataclass(frozen=True)
class RelevanceResult:
    relevant: bool
    score: float


class NullRelevanceChecker:
    """Always passes through. Used when no LLM is configured."""

    async def check(self, *, news: News, market: Market) -> RelevanceResult:
        _ = news
        _ = market
        return RelevanceResult(relevant=True, score=1.0)


class CometRelevanceChecker:
    """Stage-1: cheap LLM relevance gate before deep analysis."""

    def __init__(self, client: Any | None = None) -> None:
        self.client = client or CometAPIClient()

    async def check(self, *, news: News, market: Market) -> RelevanceResult:
        prompt = (
            "Decide whether the news item is materially relevant to predicting the "
            "outcome of the prediction-market question. Reply with strict JSON "
            'matching {"relevant": <true|false>, "score": <0..1>} and nothing else.\n'
            f"Market question: {market.question}\n"
            f"News title: {news.title}\n"
            f"News summary: {news.summary_text or ''}"
        )
        raw = await self.client.analyze_text(prompt=prompt)
        return self._parse(raw)

    @classmethod
    def _parse(cls, raw: dict[str, Any]) -> RelevanceResult:
        text = cls._extract_content_text(raw)
        payload = cls._parse_json_payload(text)
        if payload is None:
            return RelevanceResult(relevant=False, score=0.0)
        relevant = bool(payload.get("relevant", False))
        score_raw = payload.get("score", 0.0)
        try:
            score = float(score_raw)
        except (TypeError, ValueError):
            score = 0.0
        score = max(0.0, min(1.0, score))
        return RelevanceResult(relevant=relevant, score=score)

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
