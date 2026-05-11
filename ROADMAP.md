# Project Roadmap

## Purpose
This roadmap defines the end-to-end delivery plan for the Polymarket analytics and paper trading assistant, from foundation setup to MVP and post-MVP expansion.

## Scope Baseline
- In scope now: analytics signals, Telegram UI, paper trading, error review, antipattern handling, calibration and analytics.
- Out of scope now: real order execution, private key trading operations, full multi-role access control, HFT or cross-exchange arbitrage.
- Architecture requirement: all modules must be designed for later extension to real trading without rewrite.

## Delivery Principles
- Keep module boundaries strict: UI, market data, news ingestion, LLM analysis, signal engine, paper trading, review, antipatterns, analytics.
- Implement async job processing early and keep every job idempotent.
- Version strategy configs and LLM prompt templates from the first release.
- Preserve full audit trail for every signal and paper trade decision.
- Ship thin vertical slices and harden each slice before adding new complexity.

## Workstreams
- `Platform`: app skeleton, config system, environments, CI checks, migration flow.
- `Data`: schema, repositories, entity lifecycle, indexing, history retention.
- `Integrations`: Telegram, Polymarket, news sources, CometAPI.
- `Decisioning`: LLM pipeline, signal scoring, risk filtering, antipattern penalties.
- `Simulation`: paper trade lifecycle, monitoring and close logic, PnL accounting.
- `Quality`: review workflows, observability, reliability and failure handling.
- `Analytics`: calibration, win rate, edge distribution, source and antipattern analysis.

## Phase Plan

### Phase 0: Foundation and Guardrails
Goal:
- Establish deployable skeleton with module boundaries and operational basics.

Deliverables:
- Service skeleton with separated modules.
- Config management for `development` and `production`.
- Database and migration setup from [DATA_MODEL.md](./docs/DATA_MODEL.md).
- Queue and scheduler bootstrap.
- Structured logging standard and correlation IDs.

Exit criteria:
- App starts locally with bot, API, worker, and scheduler processes.
- Health checks pass.
- Core entities migrate successfully.

### Phase 1: Telegram UX and Access Layer
Goal:
- Deliver user navigation and safe access control without business logic in UI.

Deliverables:
- Inline-only Telegram navigation from [TELEGRAM_UI.md](./docs/modules/TELEGRAM_UI.md).
- Main screens: menu, signals, markets, trades, reviews, antipatterns, settings, statistics.
- Callback parsing, pagination, and expired callback handling.
- Owner-only or allowlist access control.

Exit criteria:
- End-to-end UI navigation is stable.
- Unauthorized users cannot access bot features.
- UI invokes backend services only.

### Phase 2: Market Data Pipeline
Goal:
- Build reliable Polymarket market ingestion and historical snapshot storage.

Deliverables:
- Market sync, filtering, watchlist and blacklist management.
- Snapshot polling with append-only history.
- Market archive handling for expired or unsuitable markets.

Exit criteria:
- Active markets update on schedule.
- Historical snapshots are queryable by time.
- Market data can be replayed for past signal timestamps.

### Phase 3: News Ingestion Pipeline
Goal:
- Build reliable multi-source news ingestion and normalization.

Deliverables:
- Source registry with trust score and priority.
- RSS and web ingestion adapters.
- Deduplication by canonical URL and content hash.
- Freshness metadata and topic assignment.

Exit criteria:
- News ingestion runs continuously with retries.
- Duplicate item rate is controlled.
- New records are queued for analysis.

### Phase 4: LLM Analysis Pipeline
Goal:
- Produce structured analysis outputs through staged CometAPI workflows.

Deliverables:
- Relevance check, fact extraction, entity extraction, event mapping, impact scoring, confidence estimation, contradiction detection, summary.
- Prompt template versioning.
- Analysis trace persistence.

Exit criteria:
- Structured analysis object is produced and stored for candidate news-market pairs.
- Failed jobs are retriable without data corruption.
- Model swap can be configured without business logic changes.

### Phase 5: Signal Engine and Notification Flow
Goal:
- Convert market and LLM evidence into actionable signals with risk controls.

Deliverables:
- Scoring and edge calculation from [SIGNAL_ENGINE.md](./docs/modules/SIGNAL_ENGINE.md).
- Status classification and risk flags.
- Antipattern-aware suppression and blocking.
- Signal cards surfaced in Telegram.

Exit criteria:
- Signals include strategy version, source links, and snapshot provenance.
- Duplicate signal prevention works for same evidence set.
- Users can inspect signal details and sources in UI.

### Phase 6: Paper Trading Lifecycle
Goal:
- Validate strategy quality through simulated trade execution.

Deliverables:
- Manual and auto paper trade entry modes.
- Exit rules: time, target, stop, invalidation, market close, manual close.
- Monitoring job for active trades and PnL updates.
- Full trade lifecycle persistence.

Exit criteria:
- Trades open and close deterministically.
- Entry and exit reasons are stored and visible.
- Repeated monitor runs do not create duplicate close events.

### Phase 7: Error Review and Antipattern Learning
Goal:
- Build feedback loop for systematic quality improvement.

Deliverables:
- Automatic review trigger rules.
- Manual tagging workflow in Telegram.
- Antipattern registry, assignment, and strategy penalties.
- Warning surfaces in signal and trade cards.

Exit criteria:
- Error cases can be filtered by type, market, topic, and time.
- Antipattern matches influence signal decisions.
- Review data is preserved for analytics.

### Phase 8: Analytics and Calibration
Goal:
- Provide performance visibility and probability calibration.

Deliverables:
- Signal and trade statistics.
- Calibration reports by confidence buckets.
- Source performance and antipattern impact analysis.
- Telegram statistics screens.

Exit criteria:
- Users can inspect win rate, edge distributions, and calibration.
- Analytics refresh jobs are stable and reproducible.
- Metrics support strategy tuning decisions.

### Phase 9: MVP Hardening and Release
Goal:
- Achieve production-grade stability for current scope.

Deliverables:
- Failure mode testing for external API outages.
- Retry, backoff, and deduplication validation.
- Secrets management verification.
- Deployment playbooks from [DEPLOYMENT.md](./docs/infra/DEPLOYMENT.md).

Exit criteria:
- MVP Definition of Done is satisfied.
- No critical duplicate signal or trade creation paths remain.
- End-to-end trace exists from news to signal to trade to review.

## MVP Definition of Done
- Telegram UX is inline-first and usable without slash commands.
- Markets and active signals are visible and navigable.
- News is collected and analyzed via CometAPI.
- Signals include probability, edge, confidence, and explanation.
- Paper trades are created, monitored, and closed with reason tracking.
- Manual error tagging and antipattern assignment are available.
- Historical entities are stored with full decision trace.
- System remains operational during temporary external API failures.

## Suggested Timeline (Execution-Oriented)
- Weeks 1-2: Phase 0 and Phase 1.
- Weeks 3-4: Phase 2 and Phase 3.
- Weeks 5-6: Phase 4 and Phase 5.
- Weeks 7-8: Phase 6.
- Weeks 9-10: Phase 7 and Phase 8.
- Weeks 11-12: Phase 9 hardening and MVP release.

## Critical Path Dependencies
- Data model and migrations must precede production worker jobs.
- Market snapshots and normalized news must exist before stable signal scoring.
- LLM structured output contract must stabilize before trade automation.
- Strategy config versioning must exist before meaningful analytics comparison.
- Review and antipattern linking must be present before calibration loop is complete.

## Risks and Mitigations
- Risk: external API instability. Mitigation: retries, timeout budgets, fallback statuses, and dead-letter queues.
- Risk: news quality and noise. Mitigation: source trust weighting, freshness limits, and confirmation thresholds.
- Risk: LLM output drift. Mitigation: strict structured schemas, prompt versioning, and regression checks.
- Risk: duplicate event processing. Mitigation: idempotency keys and unique constraints.
- Risk: overfitting to paper trading. Mitigation: calibration metrics and explicit review taxonomy.

## Post-MVP Expansion
- Add multi-profile strategy support with profile-level access controls.
- Add semi-auto and manual real execution gateway behind new execution module.
- Add risk limits, emergency stop, and explicit order confirmation flows.
- Add richer observability dashboards and incident playbooks.

## Reference Docs
- [SYSTEM_ARCHITECTURE.md](./docs/SYSTEM_ARCHITECTURE.md)
- [DATA_MODEL.md](./docs/DATA_MODEL.md)
- [STRATEGY_CONFIG.md](./docs/STRATEGY_CONFIG.md)
- [TELEGRAM_UI.md](./docs/modules/TELEGRAM_UI.md)
- [MARKET_DATA_MODULE.md](./docs/modules/MARKET_DATA_MODULE.md)
- [NEWS_INGESTION_MODULE.md](./docs/modules/NEWS_INGESTION_MODULE.md)
- [LLM_ANALYSIS_MODULE.md](./docs/modules/LLM_ANALYSIS_MODULE.md)
- [SIGNAL_ENGINE.md](./docs/modules/SIGNAL_ENGINE.md)
- [PAPER_TRADING_MODULE.md](./docs/modules/PAPER_TRADING_MODULE.md)
- [ERROR_REVIEW_MODULE.md](./docs/modules/ERROR_REVIEW_MODULE.md)
- [ANTIPATTERN_MODULE.md](./docs/modules/ANTIPATTERN_MODULE.md)
- [ANALYTICS_MODULE.md](./docs/modules/ANALYTICS_MODULE.md)
- [WORKER_JOBS.md](./docs/infra/WORKER_JOBS.md)
- [DEPLOYMENT.md](./docs/infra/DEPLOYMENT.md)
