from typing import Any

import httpx

from app.core.config import get_settings


_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; polymarket-assistant/0.1)",
    "Accept": "application/json",
}


class PolymarketClient:
    def __init__(self) -> None:
        settings = get_settings()
        self.gamma_base = settings.polymarket_gamma_base_url.rstrip("/")
        self.clob_base = settings.polymarket_clob_base_url.rstrip("/")
        self.data_base = settings.polymarket_data_base_url.rstrip("/")
        self._timeout = httpx.Timeout(20.0)

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=self._timeout, headers=_HEADERS)

    async def list_markets(self, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        # Default to active, liquid, top-by-volume markets so downstream stages
        # see realistic outcomes instead of the first 20 of an arbitrary order.
        effective: dict[str, Any] = {
            "active": "true",
            "closed": "false",
            "archived": "false",
            "order": "volumeNum",
            "ascending": "false",
            "limit": 200,
        }
        if params:
            effective.update(params)
        async with self._client() as client:
            response = await client.get(f"{self.gamma_base}/markets", params=effective)
            response.raise_for_status()
            payload = response.json()
            if isinstance(payload, list):
                return payload
            return payload.get("data", [])

    async def get_market_by_id(self, market_id: str) -> dict[str, Any]:
        async with self._client() as client:
            response = await client.get(f"{self.gamma_base}/markets/{market_id}")
            response.raise_for_status()
            return response.json()

    async def get_order_book(self, token_id: str) -> dict[str, Any]:
        async with self._client() as client:
            response = await client.get(f"{self.clob_base}/book", params={"token_id": token_id})
            response.raise_for_status()
            return response.json()

    async def get_midpoint(self, token_id: str) -> dict[str, Any]:
        async with self._client() as client:
            response = await client.get(f"{self.clob_base}/midpoint", params={"token_id": token_id})
            response.raise_for_status()
            return response.json()

    async def get_open_interest(self, market: str) -> dict[str, Any]:
        async with self._client() as client:
            response = await client.get(f"{self.data_base}/open-interest", params={"market": market})
            response.raise_for_status()
            return response.json()

