# Usage Examples

All examples below use public endpoints and do not require authentication.

## Events and Markets

```bash
curl --request GET \
  --url "https://gamma-api.polymarket.com/events?limit=10"
```

```bash
curl --request GET \
  --url "https://gamma-api.polymarket.com/events/slug/us-presidential-election-2028"
```

```bash
curl --request GET \
  --url "https://gamma-api.polymarket.com/markets?active=true&limit=50"
```

## Search

```bash
curl --request GET \
  --url "https://gamma-api.polymarket.com/search?q=election"
```

## Orderbook and Pricing

```bash
curl --request GET \
  --url "https://clob.polymarket.com/book?token_id=123456789"
```

```bash
curl --request GET \
  --url "https://clob.polymarket.com/price?token_id=123456789&side=BUY"
```

```bash
curl --request GET \
  --url "https://clob.polymarket.com/midpoint?token_id=123456789"
```

```bash
curl --request GET \
  --url "https://clob.polymarket.com/spread?token_id=123456789"
```

```bash
curl --request GET \
  --url "https://clob.polymarket.com/last-trade-price?token_id=123456789"
```

```bash
curl --request GET \
  --url "https://clob.polymarket.com/prices-history?market=0xabc...&startTs=1735689600&endTs=1735776000&fidelity=1h"
```

```bash
curl --request GET \
  --url "https://clob.polymarket.com/time"
```

## Data API Extras

```bash
curl --request GET \
  --url "https://data-api.polymarket.com/open-interest?market=0xabc..."
```

```bash
curl --request GET \
  --url "https://data-api.polymarket.com/live-activity-event?event_id=12345"
```

```bash
curl --request GET \
  --url "https://data-api.polymarket.com/holders?market=0xabc..."
```

## Tags and Series

```bash
curl --request GET \
  --url "https://gamma-api.polymarket.com/tags"
```

```bash
curl --request GET \
  --url "https://gamma-api.polymarket.com/tags/slug/politics/related_markets"
```

```bash
curl --request GET \
  --url "https://gamma-api.polymarket.com/series"
```

## CLOB Markets

```bash
curl --request GET \
  --url "https://clob.polymarket.com/simplified-markets?next_cursor=MA=="
```

```bash
curl --request GET \
  --url "https://clob.polymarket.com/sampling-markets?next_cursor=MA=="
```

```bash
curl --request GET \
  --url "https://clob.polymarket.com/sampling-simplified-markets"
```

## WebSocket Market Channel

Endpoint:

```text
wss://ws-subscriptions-clob.polymarket.com/ws/market
```

Example subscribe payload:

```json
{
  "assets_ids": ["123456789", "987654321"],
  "type": "market"
}
```

Message types commonly documented:
- `price_change`
- `tick_size_change`
- `last_trade_price`
- `book`
