# Endpoint Catalog

## Notes
- The table is intentionally practical: method, path, required inputs, and usage notes.
- A few docs pages show naming differences between overview pages and API-reference pages (example: `search` vs `public-search`).
- If there is a conflict, prefer API-reference pages under `docs.polymarket.com/api-reference/...`.

## Events (Gamma API)

| Endpoint | Method | Full URL (base + path) | Required Inputs | Auth | Notes |
|---|---|---|---|---|---|
| List events | `GET` | `https://gamma-api.polymarket.com/events` | none | none | Supports filtering/pagination (see API docs). |
| Get event by id | `GET` | `https://gamma-api.polymarket.com/events/{id}` | `id` (path) | none | Single event object by numeric ID. |
| Get event by slug | `GET` | `https://gamma-api.polymarket.com/events/slug/{slug}` | `slug` (path) | none | Slug-based lookup. |
| Get event tags | `GET` | `https://gamma-api.polymarket.com/events/{id}/tags` | `id` (path) | none | Event-level tags. |

## Markets (Gamma API)

| Endpoint | Method | Full URL (base + path) | Required Inputs | Auth | Notes |
|---|---|---|---|---|---|
| List markets | `GET` | `https://gamma-api.polymarket.com/markets` | none | none | Supports filtering/pagination (see API docs). |
| Get market by id | `GET` | `https://gamma-api.polymarket.com/markets/{id}` | `id` (path) | none | Single market object by numeric ID. |
| Get market by slug | `GET` | `https://gamma-api.polymarket.com/markets/slug/{slug}` | `slug` (path) | none | Slug-based market lookup. |
| Get market tags by id | `GET` | `https://gamma-api.polymarket.com/markets/{id}/tags` | `id` (path) | none | Market-level tag list. |

## Search (Gamma API)

| Endpoint | Method | Full URL (base + path) | Required Inputs | Auth | Notes |
|---|---|---|---|---|---|
| Search markets, events, profiles | `GET` | `https://gamma-api.polymarket.com/search` | `q` (query) | none | API overview also references `public-search`; verify in runtime if you need backward compatibility. |

## Orderbook and Pricing (CLOB API)

| Endpoint | Method | Full URL (base + path) | Required Inputs | Auth | Notes |
|---|---|---|---|---|---|
| Get order book | `GET` | `https://clob.polymarket.com/book` | `token_id` (query) | none | Returns bids/asks for token. |
| Get market price | `GET` | `https://clob.polymarket.com/price` | `token_id`, `side` (`BUY`/`SELL`) | none | Single-token, side-aware price. |
| Get midpoint price | `GET` | `https://clob.polymarket.com/midpoint` | `token_id` | none | Midpoint between best bid and best ask. |
| Get spread | `GET` | `https://clob.polymarket.com/spread` | `token_id` | none | Best ask - best bid spread. |
| Get last trade price | `GET` | `https://clob.polymarket.com/last-trade-price` | `token_id` | none | Most recent trade price for token. |
| Get prices history | `GET` | `https://clob.polymarket.com/prices-history` | `market` | none | Optional: `startTs`, `endTs`, `interval`, `fidelity`. |
| Get server time | `GET` | `https://clob.polymarket.com/time` | none | none | Useful for time sync and signed request windows. |

## Markets / Data Extras (Data API)

| Endpoint | Method | Full URL (base + path) | Required Inputs | Auth | Notes |
|---|---|---|---|---|---|
| Get open interest | `GET` | `https://data-api.polymarket.com/open-interest` | `market` (query) | none | Market-level open interest. |
| Get live volume for an event | `GET` | `https://data-api.polymarket.com/live-activity-event` | `event_id` (query) | none | Live event activity/volume feed-style snapshot. |
| Get top holders for markets | `GET` | `https://data-api.polymarket.com/holders` | `market` (query) | none | Holder concentration data. |

## WebSocket

| Endpoint | Protocol | URL | Auth | Notes |
|---|---|---|---|---|
| Market Channel | `WSS` | `wss://ws-subscriptions-clob.polymarket.com/ws/market` | none | Market stream updates (price_change / tick_size_change / last_trade_price / book). |

## Tags (Gamma API)

| Endpoint | Method | Full URL (base + path) | Required Inputs | Auth | Notes |
|---|---|---|---|---|---|
| List tags | `GET` | `https://gamma-api.polymarket.com/tags` | none | none | Ranked tags/categories. |
| Get tag by id | `GET` | `https://gamma-api.polymarket.com/tags/{id}` | `id` (path) | none | Single tag details. |
| Get tag by slug | `GET` | `https://gamma-api.polymarket.com/tags/slug/{slug}` | `slug` (path) | none | Slug-based tag lookup. |
| Related tags by id | `GET` | `https://gamma-api.polymarket.com/tags/{id}/related_tags` | `id` (path) | none | Related taxonomy links. |
| Related tags by slug | `GET` | `https://gamma-api.polymarket.com/tags/slug/{slug}/related_tags` | `slug` (path) | none | Slug-based related tags. |
| Related events by tag | `GET` | `https://gamma-api.polymarket.com/tags/{id}/related_events` | `id` (path) | none | Events tied to a tag. |
| Related markets by tag | `GET` | `https://gamma-api.polymarket.com/tags/{id}/related_markets` | `id` (path) | none | Markets tied to a tag. |

## Series (Gamma API)

| Endpoint | Method | Full URL (base + path) | Required Inputs | Auth | Notes |
|---|---|---|---|---|---|
| List series | `GET` | `https://gamma-api.polymarket.com/series` | none | none | Grouped event collections. |
| Get series by id | `GET` | `https://gamma-api.polymarket.com/series/{id}` | `id` (path) | none | Single series by numeric ID. |

## CLOB Markets (CLOB API)

| Endpoint | Method | Full URL (base + path) | Required Inputs | Auth | Notes |
|---|---|---|---|---|---|
| Get simplified markets | `GET` | `https://clob.polymarket.com/simplified-markets` | none (optional cursor) | none | Docs example shows `next_cursor` usage. |
| Get sampling markets | `GET` | `https://clob.polymarket.com/sampling-markets` | none (optional cursor) | none | Docs example shows `next_cursor` usage. |
| Get sampling simplified markets | `GET` | `https://clob.polymarket.com/sampling-simplified-markets` | none documented in page snapshot | none | Cursor behavior should be validated in integration tests. |
