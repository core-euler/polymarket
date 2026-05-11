from __future__ import annotations

import asyncio
from typing import Any

import feedparser

from app.db.models.entities import Source

MAX_ENTRIES_PER_FEED = 30


class RSSFetcher:
    async def fetch(self, source: Source) -> list[dict[str, Any]]:
        if source.source_type != "rss":
            return []
        loop = asyncio.get_running_loop()
        feed = await loop.run_in_executor(None, feedparser.parse, source.url)
        return [self._entry_to_dict(entry, source) for entry in feed.entries[:MAX_ENTRIES_PER_FEED]]

    @staticmethod
    def _entry_to_dict(entry: Any, source: Source) -> dict[str, Any]:
        url = getattr(entry, "link", "") or ""
        title = getattr(entry, "title", "") or ""
        summary = getattr(entry, "summary", "") or ""

        content = ""
        if hasattr(entry, "content") and entry.content:
            content = entry.content[0].get("value", "") or ""
        if not content:
            content = summary

        published_at = getattr(entry, "published", None) or getattr(entry, "updated", None)

        return {
            "url": url.strip(),
            "title": title.strip(),
            "summary": summary.strip(),
            "content": content.strip(),
            "published_at": published_at,
            "language": source.language,
            "topic": source.topic,
        }
