from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import News, Source
from app.modules.news_ingestion.rss_fetcher import RSSFetcher


class NewsIngestionModule:
    def __init__(self, source_fetcher: Any | None = None) -> None:
        self.source_fetcher = source_fetcher or RSSFetcher()

    async def sync_sources(self, session: AsyncSession) -> int:
        count = await session.scalar(
            select(func.count()).select_from(Source).where(Source.active_flag.is_(True))
        )
        return int(count or 0)

    async def ingest_news(self, session: AsyncSession) -> int:
        created = 0
        sources = list(await session.scalars(select(Source).where(Source.active_flag.is_(True))))

        for source in sources:
            try:
                raw_items = await self.source_fetcher.fetch(source)
            except Exception:
                continue

            for raw_item in raw_items:
                normalized = self._normalize_news_item(source=source, raw_item=raw_item)
                if normalized is None:
                    continue

                exists_by_url = await session.scalar(
                    select(News.id).where(News.url == normalized["url"])
                )
                if exists_by_url is not None:
                    continue

                exists_by_hash = await session.scalar(
                    select(News.id).where(
                        News.source_id == source.id,
                        News.content_hash == normalized["content_hash"],
                    )
                )
                if exists_by_hash is not None:
                    continue

                news_item = News(**normalized)
                session.add(news_item)
                created += 1

        await session.commit()
        return created

    @staticmethod
    def _parse_datetime(value: Any) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            if value.tzinfo is None:
                return value.replace(tzinfo=timezone.utc)
            return value
        if isinstance(value, str):
            cleaned = value.strip()
            if not cleaned:
                return None
            if cleaned.endswith("Z"):
                cleaned = cleaned[:-1] + "+00:00"
            try:
                parsed = datetime.fromisoformat(cleaned)
            except ValueError:
                return None
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=timezone.utc)
            return parsed
        return None

    @staticmethod
    def _hash_news_payload(content: str) -> str:
        digest = hashlib.sha256()
        digest.update(content.encode("utf-8"))
        return digest.hexdigest()

    def _normalize_news_item(self, source: Source, raw_item: dict[str, Any]) -> dict[str, Any] | None:
        url = str(raw_item.get("url") or "").strip()
        if not url:
            return None

        title = str(raw_item.get("title") or raw_item.get("headline") or url).strip()
        summary = str(raw_item.get("summary") or raw_item.get("description") or "").strip()
        content = str(raw_item.get("content") or raw_item.get("body") or summary).strip()
        published_at = self._parse_datetime(
            raw_item.get("published_at") or raw_item.get("publishedAt") or raw_item.get("pubDate")
        )
        now = datetime.now(timezone.utc)

        return {
            "source_id": source.id,
            "title": title,
            "url": url,
            "published_at": published_at,
            "discovered_at": now,
            "summary_text": summary,
            "raw_content": content,
            "language": str(raw_item.get("language") or source.language or "en"),
            "content_hash": self._hash_news_payload(content=content),
            "topic": str(raw_item.get("topic") or source.topic or ""),
            "processing_status": "new",
            "created_at": now,
        }
