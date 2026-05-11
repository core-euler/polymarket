from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Market, MarketSnapshot
from app.modules.market_data.polymarket_client import PolymarketClient


_log = structlog.get_logger("market_data")

# When CLOB has no live midpoint, the gamma fallback is the only price we have.
# For a market that has not actually resolved, a value at the [0,1] boundaries
# almost always means stale/garbage data (one tiny trade, dead book, or Gamma
# returning a settled-shape payload). Persisting it would let downstream paper
# trades close at fake +/- extremes. Reject the tick instead.
_EXTREME_LOW = 0.02
_EXTREME_HIGH = 0.98


class MarketDataModule:
    def __init__(
        self,
        polymarket_client: PolymarketClient | Any | None = None,
        *,
        clob_concurrency: int = 16,
    ) -> None:
        self.polymarket_client = polymarket_client or PolymarketClient()
        self.clob_concurrency = max(1, clob_concurrency)

    async def sync_markets(self, session: AsyncSession) -> int:
        raw_markets = await self.polymarket_client.list_markets()
        processed = 0

        for payload in raw_markets:
            polymarket_id = self._extract_market_id(payload)
            if not polymarket_id:
                continue

            market = await session.scalar(
                select(Market).where(Market.polymarket_id == polymarket_id)
            )
            if market is None:
                market = Market(
                    polymarket_id=polymarket_id,
                    slug="",
                    title="",
                    question="",
                    topic="",
                    status="active",
                )
                session.add(market)

            self._apply_market_payload(market=market, payload=payload)
            processed += 1

        await session.commit()
        return processed

    async def capture_snapshots(self, session: AsyncSession) -> int:
        stmt = select(Market).where(
            Market.status == "active",
            Market.archived_flag.is_(False),
            Market.blacklist_flag.is_(False),
        )
        markets = list(await session.scalars(stmt))
        if not markets:
            return 0

        gamma_index = await self._build_gamma_index()
        eligible = [m for m in markets if str(m.polymarket_id) in gamma_index]
        _log.info(
            "capture_snapshots.start",
            total_markets=len(markets),
            with_gamma=len(eligible),
            clob_concurrency=self.clob_concurrency,
        )
        if not eligible:
            return 0

        semaphore = asyncio.Semaphore(self.clob_concurrency)
        now = datetime.now(timezone.utc)
        results = await asyncio.gather(
            *(
                self._build_snapshot(market, gamma_index[str(market.polymarket_id)], semaphore, now)
                for market in eligible
            )
        )

        snapshots = [snapshot for snapshot in results if snapshot is not None]
        rejected = len(results) - len(snapshots)
        for snapshot in snapshots:
            session.add(snapshot)

        await session.commit()
        _log.info(
            "capture_snapshots.done",
            snapshots=len(snapshots),
            rejected_extreme=rejected,
        )
        return len(snapshots)

    async def _build_snapshot(
        self,
        market: Market,
        gamma_payload: dict[str, Any],
        semaphore: asyncio.Semaphore,
        now: datetime,
    ) -> MarketSnapshot | None:
        yes_price = self._extract_yes_price(gamma_payload)
        liquidity = self._extract_numeric(
            gamma_payload,
            keys=["liquidityNum", "liquidity_num", "liquidityClob", "liquidity"],
            default=0.0,
        )
        volume = self._extract_numeric(
            gamma_payload,
            keys=["volume24hrClob", "volume24hr", "volumeClob", "volume"],
            default=0.0,
        )
        best_bid = self._to_float(gamma_payload.get("bestBid"))
        best_ask = self._to_float(gamma_payload.get("bestAsk"))
        spread_from_gamma = self._to_float(gamma_payload.get("spread"))

        clob_payload: dict[str, Any] = {}
        clob_mid = 0.0
        if market.yes_token_id:
            async with semaphore:
                try:
                    midpoint_payload = await self.polymarket_client.get_midpoint(
                        token_id=market.yes_token_id
                    )
                except Exception:
                    midpoint_payload = {}
                try:
                    book_payload = await self.polymarket_client.get_order_book(
                        token_id=market.yes_token_id
                    )
                except Exception:
                    book_payload = {}
            clob_payload = {"midpoint": midpoint_payload, "book": book_payload}

            clob_mid = self._extract_midpoint(midpoint_payload)
            if clob_mid > 0:
                yes_price = clob_mid
            clob_bid = self._extract_best_price(book_payload.get("bids"), prefer_max=True)
            clob_ask = self._extract_best_price(book_payload.get("asks"), prefer_max=False)
            if clob_bid is not None:
                best_bid = clob_bid
            if clob_ask is not None:
                best_ask = clob_ask

        if best_bid is not None and best_ask is not None:
            spread = max(best_ask - best_bid, 0.0)
        elif spread_from_gamma is not None:
            spread = max(spread_from_gamma, 0.0)
        else:
            spread = 0.0

        # Reject the snapshot when CLOB had no live midpoint AND the only price
        # we have is at the [0,1] boundaries. That is almost always stale/dead
        # market data, not a real probability signal. Better to skip the tick.
        if clob_mid <= 0 and (yes_price <= _EXTREME_LOW or yes_price >= _EXTREME_HIGH):
            _log.warning(
                "snapshot_rejected.extreme_price_no_clob_midpoint",
                market_id=market.id,
                polymarket_id=market.polymarket_id,
                yes_price=yes_price,
                liquidity=liquidity,
            )
            return None

        return MarketSnapshot(
            market_id=market.id,
            captured_at=now,
            last_price=yes_price,
            implied_probability=yes_price,
            liquidity=liquidity,
            spread=spread,
            volume=volume,
            raw_payload={"gamma": gamma_payload, "clob": clob_payload},
        )

    async def _build_gamma_index(self) -> dict[str, dict[str, Any]]:
        try:
            payloads = await self.polymarket_client.list_markets()
        except Exception:
            return {}
        index: dict[str, dict[str, Any]] = {}
        for payload in payloads:
            market_id = self._extract_market_id(payload)
            if market_id:
                index[market_id] = payload
        return index

    @classmethod
    def _extract_yes_price(cls, payload: dict[str, Any]) -> float:
        outcome_prices = payload.get("outcomePrices")
        if isinstance(outcome_prices, str):
            try:
                outcome_prices = json.loads(outcome_prices)
            except json.JSONDecodeError:
                outcome_prices = None
        if isinstance(outcome_prices, list) and outcome_prices:
            converted = cls._to_float(outcome_prices[0])
            if converted is not None:
                return converted
        for key in ("lastTradePrice", "bestBid", "bestAsk"):
            converted = cls._to_float(payload.get(key))
            if converted is not None:
                return converted
        return 0.0

    @staticmethod
    def _extract_market_id(payload: dict[str, Any]) -> str:
        value = payload.get("id") or payload.get("market_id") or payload.get("conditionId")
        if value is None:
            return ""
        return str(value).strip()

    @staticmethod
    def _parse_datetime(value: Any) -> datetime | None:
        if not value:
            return None
        if isinstance(value, datetime):
            if value.tzinfo is None:
                return value.replace(tzinfo=timezone.utc)
            return value
        if isinstance(value, str):
            normalized = value.strip()
            if normalized.endswith("Z"):
                normalized = normalized[:-1] + "+00:00"
            try:
                dt = datetime.fromisoformat(normalized)
            except ValueError:
                return None
            if dt.tzinfo is None:
                return dt.replace(tzinfo=timezone.utc)
            return dt
        return None

    @staticmethod
    def _to_float(value: Any) -> float | None:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            stripped = value.strip()
            if stripped == "":
                return None
            try:
                return float(stripped)
            except ValueError:
                return None
        return None

    @classmethod
    def _extract_numeric(cls, payload: dict[str, Any], keys: list[str], default: float = 0.0) -> float:
        for key in keys:
            value = payload.get(key)
            converted = cls._to_float(value)
            if converted is not None:
                return converted
        return default

    @classmethod
    def _extract_midpoint(cls, payload: dict[str, Any]) -> float:
        for key in ("mid", "midpoint", "price", "value"):
            converted = cls._to_float(payload.get(key))
            if converted is not None:
                return converted
        return 0.0

    @classmethod
    def _extract_best_price(cls, rows: Any, prefer_max: bool) -> float | None:
        if not isinstance(rows, list):
            return None
        prices: list[float] = []
        for row in rows:
            if isinstance(row, dict):
                value = row.get("price")
            elif isinstance(row, (list, tuple)) and row:
                value = row[0]
            else:
                value = None
            converted = cls._to_float(value)
            if converted is not None:
                prices.append(converted)
        if not prices:
            return None
        return max(prices) if prefer_max else min(prices)

    @staticmethod
    def _resolve_status(payload: dict[str, Any], current_status: str) -> str:
        if payload.get("closed") is True:
            return "closed"
        if payload.get("active") is True:
            return "active"
        if payload.get("active") is False:
            return "inactive"
        raw_status = payload.get("status")
        if raw_status:
            return str(raw_status)
        return current_status or "active"

    def _apply_market_payload(self, market: Market, payload: dict[str, Any]) -> None:
        slug = str(payload.get("slug") or market.slug or "")
        question = str(payload.get("question") or payload.get("title") or market.question or "")
        title = str(payload.get("title") or payload.get("question") or market.title or question)
        topic = str(payload.get("topic") or payload.get("category") or market.topic or "")
        status = self._resolve_status(payload=payload, current_status=market.status)
        expires_at = self._parse_datetime(
            payload.get("endDate")
            or payload.get("end_date")
            or payload.get("expiresAt")
            or payload.get("expirationTime")
        )

        market.slug = slug
        market.question = question or title or market.polymarket_id
        market.title = title or market.question
        market.topic = topic
        market.status = status
        if expires_at is not None:
            market.expires_at = expires_at

        yes_token, no_token = self._extract_clob_token_ids(payload)
        if yes_token:
            market.yes_token_id = yes_token
        if no_token:
            market.no_token_id = no_token

    @staticmethod
    def _extract_clob_token_ids(payload: dict[str, Any]) -> tuple[str | None, str | None]:
        raw = payload.get("clobTokenIds")
        if raw is None:
            return None, None
        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                return None, None
        else:
            parsed = raw
        if not isinstance(parsed, list):
            return None, None
        yes = str(parsed[0]) if len(parsed) > 0 and parsed[0] else None
        no = str(parsed[1]) if len(parsed) > 1 and parsed[1] else None
        return yes, no
