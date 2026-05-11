# Polymarket API Notes

Last verified: `2026-03-13` (from official Polymarket docs).

This folder contains a practical endpoint map for the APIs used by this project:
- Gamma API (`https://gamma-api.polymarket.com`) for events, markets, tags, series, discovery
- CLOB API (`https://clob.polymarket.com`) for order book and pricing
- Data API (`https://data-api.polymarket.com`) for open interest, volume/activity, holders
- WebSocket (`wss://ws-subscriptions-clob.polymarket.com/ws/market`) for market stream

Authentication:
- All endpoints documented in this folder are public market-data/discovery endpoints (no auth required).
- Trading/order-management endpoints are separate and require Polymarket auth headers.

Contents:
- [ENDPOINTS.md](./ENDPOINTS.md): grouped endpoint catalog for Events, Markets, Search, pricing/orderbook, tags, series, CLOB markets, and WebSocket.
- [EXAMPLES.md](./EXAMPLES.md): ready-to-run curl and websocket examples.
- [SOURCES.md](./SOURCES.md): source links used during verification.
