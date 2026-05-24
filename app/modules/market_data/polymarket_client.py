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

    async def list_resolved_markets(
        self,
        *,
        page_size: int = 500,
        max_pages: int = 40,
        extra: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Paginate Gamma for CLOSED (resolved) markets, highest-volume first.

        Used by the offline FLB replay to build a survivorship-free universe:
        every market that resolved in the window, winners and losers alike.
        """
        base: dict[str, Any] = {
            "closed": "true",
            "active": "false",
            "archived": "false",
            "order": "volumeNum",
            "ascending": "false",
            "limit": page_size,
        }
        if extra:
            base.update(extra)
        out: list[dict[str, Any]] = []
        async with self._client() as client:
            for page in range(max_pages):
                params = {**base, "offset": page * page_size}
                response = await client.get(f"{self.gamma_base}/markets", params=params)
                # Gamma 422s once the offset runs past the result set — that is
                # the end of pagination, not an error worth aborting on.
                if response.status_code == 422:
                    break
                response.raise_for_status()
                payload = response.json()
                rows = payload if isinstance(payload, list) else payload.get("data", [])
                if not rows:
                    break
                out.extend(rows)
        return out

    # CLOB rejects startTs/endTs spans beyond ~14d ("interval is too long"),
    # independent of fidelity, so longer ranges are fetched in chunks.
    _HISTORY_MAX_SPAN_S = 13 * 86400

    @classmethod
    def _history_windows(
        cls, start_ts: int | None, end_ts: int | None
    ) -> list[tuple[int | None, int | None]]:
        if start_ts is None or end_ts is None:
            return [(start_ts, end_ts)]
        if end_ts - start_ts <= cls._HISTORY_MAX_SPAN_S:
            return [(start_ts, end_ts)]
        windows: list[tuple[int | None, int | None]] = []
        cursor = start_ts
        while cursor < end_ts:
            nxt = min(cursor + cls._HISTORY_MAX_SPAN_S, end_ts)
            windows.append((cursor, nxt))
            cursor = nxt
        return windows

    async def get_prices_history(
        self,
        token_id: str,
        *,
        start_ts: int | None = None,
        end_ts: int | None = None,
        fidelity: int = 60,
    ) -> list[dict[str, Any]]:
        """CLOB price time-series for a token. Returns [{"t": epoch, "p": price}].

        Long ranges are split into <=13d windows and stitched (deduped by t),
        since the CLOB caps the span of a single startTs/endTs query.
        """
        merged: dict[int, float] = {}
        async with self._client() as client:
            for ws, we in self._history_windows(start_ts, end_ts):
                params: dict[str, Any] = {"market": token_id, "fidelity": fidelity}
                if ws is not None:
                    params["startTs"] = ws
                if we is not None:
                    params["endTs"] = we
                response = await client.get(
                    f"{self.clob_base}/prices-history", params=params
                )
                if response.status_code >= 400:
                    continue  # a dead chunk shouldn't sink the whole series
                payload = response.json()
                rows = payload.get("history", []) if isinstance(payload, dict) else []
                for h in rows:
                    if h.get("t") is not None and h.get("p") is not None:
                        merged[int(h["t"])] = float(h["p"])
        return [{"t": t, "p": merged[t]} for t in sorted(merged)]

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

