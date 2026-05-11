from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from app.db.models import Market, News


_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9'-]*", re.IGNORECASE)

# Minimal English stopword set. Tuned for short news titles + market questions.
_STOPWORDS: frozenset[str] = frozenset(
    {
        "a", "an", "the", "and", "or", "but", "if", "then", "else",
        "of", "in", "on", "at", "to", "for", "from", "by", "with", "as",
        "is", "are", "was", "were", "be", "been", "being",
        "this", "that", "these", "those", "it", "its",
        "will", "would", "could", "should", "can", "may", "might", "do", "does", "did",
        "have", "has", "had", "having",
        "not", "no", "yes", "than", "into", "over", "under", "again",
        "any", "all", "some", "such", "more", "most", "other",
        "so", "very", "just", "about", "before", "after", "between",
        "i", "you", "he", "she", "we", "they", "them", "his", "her", "their", "our",
        "what", "which", "who", "whom", "where", "when", "why", "how",
    }
)


@dataclass(frozen=True)
class CandidateMatch:
    market: Market
    score: float
    overlap: tuple[str, ...]


class KeywordFilter:
    """Stage-0 cheap pre-filter: rank markets by token overlap with a news item.

    No external calls. The goal is to cut the (news x market) fan-out before
    any LLM-bound stage runs.
    """

    def __init__(self, *, top_k: int = 3, min_score: float = 0.05) -> None:
        if top_k < 1:
            raise ValueError("top_k must be >= 1")
        if min_score < 0:
            raise ValueError("min_score must be >= 0")
        self.top_k = top_k
        self.min_score = min_score

    def rank_candidates(self, *, news: News, markets: Iterable[Market]) -> list[CandidateMatch]:
        news_tokens = self._tokenize(self._news_text(news))
        if not news_tokens:
            return []

        candidates: list[CandidateMatch] = []
        for market in markets:
            market_tokens = self._tokenize(self._market_text(market))
            if not market_tokens:
                continue
            overlap = news_tokens & market_tokens
            if not overlap:
                continue
            score = self._score(news_tokens=news_tokens, market_tokens=market_tokens, overlap=overlap)
            if score < self.min_score:
                continue
            candidates.append(
                CandidateMatch(market=market, score=score, overlap=tuple(sorted(overlap)))
            )

        candidates.sort(key=lambda item: item.score, reverse=True)
        return candidates[: self.top_k]

    @staticmethod
    def _news_text(news: News) -> str:
        parts = [news.title or "", news.summary_text or "", news.raw_content or ""]
        return " ".join(part for part in parts if part)

    @staticmethod
    def _market_text(market: Market) -> str:
        parts = [market.title or "", market.question or "", market.topic or ""]
        return " ".join(part for part in parts if part)

    @classmethod
    def _tokenize(cls, text: str) -> set[str]:
        if not text:
            return set()
        tokens = _TOKEN_RE.findall(text.lower())
        return {tok for tok in tokens if len(tok) > 2 and tok not in _STOPWORDS}

    @staticmethod
    def _score(
        *, news_tokens: set[str], market_tokens: set[str], overlap: set[str]
    ) -> float:
        # Weighted blend: Jaccard captures shared specificity, coverage rewards
        # markets whose tokens are heavily represented in the news.
        union = news_tokens | market_tokens
        jaccard = len(overlap) / len(union) if union else 0.0
        market_coverage = len(overlap) / len(market_tokens) if market_tokens else 0.0
        return 0.5 * jaccard + 0.5 * market_coverage
