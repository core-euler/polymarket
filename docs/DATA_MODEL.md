# Data Model

## Module responsibility
Define the canonical database entities, required fields, relationships, and lifecycle rules. This document exists to keep schema generation consistent across manual and LLM-assisted development.

## Module inputs
- Requirements from system architecture and module specs
- Persistent audit, replay, and analytics requirements

## Module outputs
- Entity list
- Required fields per entity
- Relationship map
- Lifecycle expectations

## Dependencies
- [SYSTEM_ARCHITECTURE.md](./SYSTEM_ARCHITECTURE.md)
- [STRATEGY_CONFIG.md](./STRATEGY_CONFIG.md)
- Module docs under `docs/modules/`

## Data modeling principles
- Use stable internal IDs even when external IDs exist.
- Store enough history to reconstruct the state used for each decision.
- Treat strategy versions, prompt template versions, and source metadata as first-class data.
- Prefer append-only history for market snapshots, analyses, signals, trades, and reviews.
- Use explicit status fields instead of inferring lifecycle state from nullable timestamps.

## Entity relationships
- `users` own manual actions such as reviews, ignored signals, and strategy changes.
- `markets` have many `market_snapshots`.
- `sources` have many `news` items.
- `news` can have many `llm_analyses`.
- `markets` can have many `llm_analyses`.
- `signals` belong to one `market` and reference one snapshot baseline.
- `signals` relate to many `news` items and many `llm_analyses`.
- `paper_trades` belong to one `signal` and one `market`.
- `error_reviews` can target a `signal`, a `paper_trade`, or both.
- `antipatterns` relate to many `signals` through `signal_antipatterns`.
- `strategy_configs` version the logic used by `signals` and `paper_trades`.

## Core entities

### users
Required fields:
- `id`
- `telegram_id`
- `username`
- `role`
- `access_status`
- `notification_settings`
- `created_at`
- `updated_at`

Lifecycle:
- Created when a trusted user is registered.
- Updated when access or notification settings change.
- Soft-disabled instead of deleted when access is revoked.

### markets
Required fields:
- `id`
- `polymarket_id`
- `slug`
- `title`
- `question`
- `topic`
- `status`
- `created_at`
- `expires_at`
- `watchlist_flag`
- `blacklist_flag`
- `archived_flag`
- `updated_at`

Lifecycle:
- Created from Polymarket sync.
- Updated as metadata changes.
- Archived when expired, closed, or explicitly removed from active processing.

### market_snapshots
Required fields:
- `id`
- `market_id`
- `captured_at`
- `last_price`
- `implied_probability`
- `liquidity`
- `spread`
- `volume`
- `raw_payload`

Lifecycle:
- Append-only records captured by polling jobs.
- Never updated in place except for repair or backfill workflows.
- Used as historical evidence for signals and trade events.

### sources
Required fields:
- `id`
- `name`
- `source_type`
- `url`
- `domain`
- `topic`
- `language`
- `trust_score`
- `priority`
- `active_flag`
- `created_at`
- `updated_at`

Lifecycle:
- Created from source registry configuration.
- Updated when trust score, priority, or status changes.
- Retained for audit even if disabled.

### news
Required fields:
- `id`
- `source_id`
- `title`
- `url`
- `published_at`
- `discovered_at`
- `summary_text`
- `raw_content`
- `language`
- `content_hash`
- `topic`
- `processing_status`
- `created_at`

Lifecycle:
- Created after fetch and normalization.
- Deduplicated by canonical URL and content hash.
- Moves through statuses such as `new`, `queued`, `analyzed`, `ignored`, or `failed`.

### llm_analyses
Required fields:
- `id`
- `news_id`
- `market_id`
- `model_name`
- `prompt_template_version`
- `relevance`
- `event_time`
- `impact_direction`
- `impact_strength`
- `confidence`
- `facts_json`
- `entities_json`
- `uncertainties_json`
- `contradictions_json`
- `summary`
- `trace_json`
- `created_at`

Lifecycle:
- Created after a full or partial LLM pipeline execution.
- Multiple analyses may exist for the same news item across markets or model versions.
- Must remain immutable for auditability.

### signals
Required fields:
- `id`
- `market_id`
- `snapshot_id`
- `market_probability`
- `model_probability`
- `edge`
- `confidence`
- `status`
- `explanation`
- `risk_flags_json`
- `strategy_config_id`
- `strategy_version`
- `created_at`

Lifecycle:
- Created when the signal engine decides a candidate is material enough to persist.
- Can transition between active and resolved views but should preserve original decision data.
- Must remain linked to the market snapshot and analyses used at decision time.

### signal_news
Required fields:
- `signal_id`
- `news_id`

Lifecycle:
- Created with signal persistence.
- Provides explicit provenance for each signal.

### signal_analyses
Required fields:
- `signal_id`
- `llm_analysis_id`

Lifecycle:
- Created with signal persistence.
- Supports replay and detailed trace views.

### paper_trades
Required fields:
- `id`
- `signal_id`
- `market_id`
- `direction`
- `entry_price`
- `position_size`
- `open_time`
- `status`
- `open_reason`
- `strategy_config_id`
- `strategy_version`

Recommended close-time fields:
- `exit_price`
- `close_time`
- `close_reason`
- `realized_pnl`
- `holding_duration_seconds`

Lifecycle:
- Created from manual or automatic paper trade entry.
- Updated during monitoring with current status and optional unrealized metrics.
- Closed once an exit rule or manual closure is applied.

### error_reviews
Required fields:
- `id`
- `review_target_type`
- `review_target_id`
- `error_type`
- `severity`
- `origin`
- `comment`
- `created_by_user_id`
- `created_at`

Lifecycle:
- Created automatically by rules or manually by the user.
- May be reclassified or annotated later.
- Must remain queryable by error type, market, topic, and outcome.

### antipatterns
Required fields:
- `id`
- `code`
- `name`
- `description`
- `detection_logic_description`
- `penalty_action`
- `penalty_value`
- `active_flag`
- `created_at`
- `updated_at`

Lifecycle:
- Created manually or seeded as known failure patterns.
- Updated as detection logic and penalty values evolve.
- Soft-disabled when retired.

### signal_antipatterns
Required fields:
- `signal_id`
- `antipattern_id`
- `assignment_mode`
- `comment`
- `created_at`

Lifecycle:
- Created when an antipattern is detected or manually assigned.
- Retained permanently for audit and analytics.

### strategy_configs
Required fields:
- `id`
- `profile_name`
- `version`
- `parameters_json`
- `paper_trading_rules_json`
- `antipattern_rules_json`
- `active_flag`
- `created_at`

Lifecycle:
- New records are inserted for every strategy change.
- Existing versions remain immutable once used by signals or trades.
- Exactly one active profile per environment is recommended unless multi-profile behavior is implemented.

## Lifecycle notes
- Market data is historical and append-oriented.
- News is normalized once, then enriched by analysis and downstream linkage.
- LLM analyses are immutable evidence.
- Signals capture a point-in-time decision and should not be rewritten to match later information.
- Paper trades are stateful but must preserve entry and exit evidence.
- Reviews and antipattern assignments are additive learning layers, not replacements for original signal data.
- Strategy configs are versioned records, not mutable global settings.

## Required audit links
- Every signal must reference its market snapshot and strategy version.
- Every paper trade must reference its originating signal and strategy version.
- Every review should be traceable back to the triggering signal or trade.
- Every antipattern assignment should identify whether it was automatic or manual.

## Suggested indexing
- `markets.polymarket_id`
- `market_snapshots (market_id, captured_at)`
- `news.content_hash`
- `news (source_id, published_at)`
- `llm_analyses (news_id, market_id, created_at)`
- `signals (market_id, created_at, status)`
- `paper_trades (market_id, status, open_time)`
- `error_reviews (error_type, created_at)`
- `signal_antipatterns (antipattern_id, created_at)`
- `strategy_configs (profile_name, version)`
