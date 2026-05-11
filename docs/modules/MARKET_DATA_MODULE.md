# Market Data Module

## Module responsibility
Fetch, store, and expose Polymarket market data and historical snapshots for downstream modules.

## Module inputs
- Polymarket market metadata
- Polymarket price and liquidity updates
- Watchlist and blacklist commands from application services

## Module outputs
- Normalized market records
- Time-based market snapshots
- Filtered market lists
- Market lookup APIs for downstream consumers

## Dependencies
- Polymarket market data APIs
- Database
- Scheduler or worker layer

## Hard boundary
This module does not know about:
- News ingestion
- LLM analysis
- Signal scoring
- Paper trade decisions

## Responsibilities
- Fetch markets
- Update market status
- Store market snapshots
- Filter markets by status, topic, liquidity, and expiry
- Manage watchlist state
- Manage blacklist state
- Archive expired or unsuitable markets

## Managed data
- Market metadata
- Current implied probability
- Last price
- Liquidity
- Spread
- Volume if available
- Time-based snapshots
- Local watchlist and blacklist flags

## Core workflows

### Market discovery
- Pull active and relevant markets from Polymarket.
- Normalize identifiers and key metadata.
- Insert new records or update existing records.

### Snapshot polling
- Poll active markets on a schedule.
- Persist append-only snapshots with capture time.
- Skip or slow down archived and blacklisted markets.

### Market filtering
- Expose filters for:
- Topic
- Status
- Time to expiry
- Liquidity
- Watchlist membership
- Blacklist membership
- Archive state

### State management
- Support manual watchlist inclusion.
- Support automatic watchlist rules by topic.
- Support manual ignore or blacklist actions.
- Archive expired or irrelevant markets without deleting history.

## Required interfaces
- `syncMarkets()`
- `getMarketById()`
- `listMarkets(filters)`
- `captureSnapshot(marketId)`
- `listSnapshots(marketId, range)`
- `setWatchlistState(marketId, state)`
- `setBlacklistState(marketId, state)`
- `archiveMarket(marketId, reason)`

## Reliability rules
- Handle upstream API failures with retries and backoff.
- Deduplicate repeated sync results.
- Never overwrite historical snapshots.
- Preserve the exact snapshot used for each downstream decision.
