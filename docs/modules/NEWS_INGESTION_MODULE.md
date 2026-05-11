# News Ingestion Module

## Module responsibility
Collect, normalize, deduplicate, and store news items and source metadata for later analysis.

## Module inputs
- Source registry definitions
- RSS feeds
- Web pages or structured web feeds
- Topic mapping rules

## Module outputs
- Normalized news records
- Source metadata and trust scores
- Deduplication keys
- Freshness metadata
- Topic assignments

## Dependencies
- Source registry configuration
- HTTP fetching and feed parsing adapters
- Database
- Scheduler or worker layer

## Hard boundary
This module only collects and prepares news. It does not:
- Perform LLM reasoning
- Decide market relevance
- Score signals
- Trigger trading actions directly

## Responsibilities
- Collect RSS feeds
- Collect web sources
- Normalize metadata
- Store raw content
- Deduplicate news items
- Assign topics
- Maintain source registry state

## Source registry
Each source should define:
- Name
- Source type
- URL
- Domain
- Topic coverage
- Language
- Trust score
- Priority
- Active flag

## Freshness logic
- Compute time since publication and time since discovery.
- Penalize or exclude stale content based on strategy needs.
- Preserve raw timestamps even when freshness scores change later.

## Topic classification
- Assign coarse topics such as politics, regulation, elections, sports, crypto, or macro.
- Support rule-based topic assignment first.
- Allow later enrichment by downstream analysis without mutating original ingestion metadata.

## Deduplication rules
- Use canonical URL normalization where possible.
- Compute content hash from normalized title and body text.
- Prefer marking duplicates instead of deleting them.
- Preserve source diversity even when multiple sources cover the same event.

## Normalized news record
Minimum fields:
- Source ID
- Title
- URL
- Published time
- Discovered time
- Summary text
- Raw content
- Language
- Content hash
- Topic
- Processing status

## Required interfaces
- `syncSources()`
- `fetchSource(sourceId)`
- `ingestNewsItem(payload)`
- `deduplicateNewsItem(newsId)`
- `listNews(filters)`
- `getNewsById(newsId)`
- `markNewsStatus(newsId, status)`

## Reliability rules
- Source failures must not stop the whole pipeline.
- Fetch retries should be bounded and logged.
- Broken sources should be marked unhealthy without deleting prior data.
- News ingestion must be idempotent across repeated polls.
