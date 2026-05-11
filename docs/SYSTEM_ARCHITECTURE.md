# System Architecture

## Module responsibility
Provide the top-level architecture for the Polymarket analytics and paper trading assistant. This document is the entry point for developers and LLM tools.

## Module inputs
- Product requirements from `SPEC.md`
- External platform constraints from Telegram, Polymarket, CometAPI, RSS/web sources, database, and queue infrastructure

## Module outputs
- System decomposition into bounded modules
- End-to-end data and event flows
- Lifecycle definitions for signals and paper trades
- Integration boundaries and dependency rules

## Dependencies
- [DATA_MODEL.md](./DATA_MODEL.md)
- [STRATEGY_CONFIG.md](./STRATEGY_CONFIG.md)
- [TELEGRAM_UI.md](./modules/TELEGRAM_UI.md)
- [MARKET_DATA_MODULE.md](./modules/MARKET_DATA_MODULE.md)
- [NEWS_INGESTION_MODULE.md](./modules/NEWS_INGESTION_MODULE.md)
- [LLM_ANALYSIS_MODULE.md](./modules/LLM_ANALYSIS_MODULE.md)
- [SIGNAL_ENGINE.md](./modules/SIGNAL_ENGINE.md)
- [PAPER_TRADING_MODULE.md](./modules/PAPER_TRADING_MODULE.md)
- [ERROR_REVIEW_MODULE.md](./modules/ERROR_REVIEW_MODULE.md)
- [ANTIPATTERN_MODULE.md](./modules/ANTIPATTERN_MODULE.md)
- [ANALYTICS_MODULE.md](./modules/ANALYTICS_MODULE.md)
- [WORKER_JOBS.md](./infra/WORKER_JOBS.md)
- [DEPLOYMENT.md](./infra/DEPLOYMENT.md)

## Project overview
The system is a Telegram-first assistant for Polymarket market monitoring, news-driven analysis, structured LLM reasoning, signal generation, paper trading, and post-trade review. The current scope is limited to analytics and simulated trading. Real trade execution is explicitly out of scope for the current stage, but the architecture must support a later execution module without a rewrite.

## Architectural principles
- Keep Telegram UI separate from business logic.
- Keep market ingestion, news ingestion, LLM analysis, strategy, and paper trading in separate modules.
- Make every decision auditable through stored inputs, intermediate traces, and versioned strategy configuration.
- Run long operations asynchronously through worker jobs.
- Make modules replaceable behind stable interfaces.
- Design all background jobs to be idempotent and retry-safe.
- Prevent duplicate signals and duplicate paper trades.
- Preserve enough historical state to reconstruct any signal decision.

## System components
- Telegram UI module: renders menus, cards, callbacks, and navigation only.
- Auth/access module: enforces owner-only or allowlist access.
- Market data module: loads Polymarket markets, updates snapshots, and manages watchlist/blacklist/archive state.
- News ingestion module: collects, normalizes, deduplicates, and stores news content.
- LLM analysis module: performs structured analysis through CometAPI and stores analysis traces.
- Signal engine: combines market data, LLM outputs, source metadata, and strategy configuration into signals.
- Paper trading module: simulates entries, exits, PnL, and trade lifecycle state.
- Error review module: records automatic and manual review findings for bad outcomes or suspicious cases.
- Antipattern module: stores recurring failure patterns and applies penalties or blocks.
- Analytics module: computes calibration, win rate, edge distribution, source performance, and antipattern statistics.
- Scheduler/worker layer: runs periodic refresh, analysis, signal generation, monitoring, and analytics jobs.
- Storage layer: database for entities and Redis/queue for asynchronous jobs and deduplication.

## Data flow
1. The market data module ingests Polymarket metadata and periodic market snapshots.
2. The news ingestion module pulls active sources, normalizes content, deduplicates records, and assigns topics.
3. The worker layer sends candidate news items to the LLM analysis module.
4. The LLM analysis module produces structured relevance, facts, entities, impact, confidence, and summary results.
5. The signal engine joins current market state, historical snapshots, normalized news, LLM analysis, strategy configuration, and antipattern rules.
6. The signal engine writes signals and exposes them to Telegram UI and downstream paper trading logic.
7. The paper trading module opens and monitors simulated positions for eligible signals.
8. The review and antipattern modules capture failures and feed penalties back into future signal scoring.
9. The analytics module aggregates outcomes for user-visible statistics and calibration.

## Event flow
1. Scheduler refreshes markets and source feeds.
2. New or updated records are stored with timestamps and deduplication keys.
3. Relevant news is queued for LLM analysis.
4. Completed analysis events trigger signal evaluation.
5. Signal creation may trigger Telegram notification and optional paper trade creation.
6. Active trades are monitored on schedule until exit conditions are met.
7. Closed trades and reviewed cases update analytics and antipattern statistics.

## Module dependencies
- Telegram UI depends on backend services only. It must not call external market, news, or LLM providers directly.
- Market data depends on Polymarket and storage only.
- News ingestion depends on source registry, fetchers, and storage only.
- LLM analysis depends on CometAPI, market context lookup, prompt templates, and storage.
- Signal engine depends on market data, normalized news metadata, LLM analysis, strategy config, and antipattern evaluation.
- Paper trading depends on signal outputs, market snapshots, and strategy configuration.
- Error review depends on signals, paper trades, news, and source metadata.
- Antipattern depends on signal context, review history, and rule definitions.
- Analytics depends on persisted signals, trades, reviews, antipatterns, and market outcomes.

## Signal lifecycle
1. Candidate creation: a market and one or more fresh news items form an analysis candidate.
2. Relevance screening: the LLM module decides whether the news can affect the market.
3. Structured analysis: facts, entities, event mapping, impact direction, impact strength, and confidence are produced.
4. Scoring: the signal engine compares model probability against market probability and computes edge.
5. Risk filtering: confidence thresholds, liquidity rules, freshness limits, source confirmation requirements, and antipattern penalties are applied.
6. Classification: the signal receives a status such as `informational`, `weak_signal`, `valid_signal`, `paper_trade_candidate`, `suppressed_by_risk`, or `blocked_by_antipattern`.
7. Persistence: the full signal object stores market snapshot, source set, LLM analyses, explanation, and strategy version.
8. Delivery: the Telegram UI may show the signal and optional paper trade action.
9. Review: after market evolution or trade outcome, the signal can be linked to error reviews and antipatterns.

## Paper trade lifecycle
1. Eligibility: the signal engine marks a signal as eligible for manual or automatic paper trading.
2. Entry: the paper trading module opens a virtual position with direction, size, entry price, and open reason.
3. Monitoring: periodic jobs update unrealized PnL, holding time, and exit-condition checks.
4. Exit: the trade closes by target, stop, time expiry, signal invalidation, market close, or manual action.
5. Settlement: the trade stores final PnL, close reason, and closing market snapshot.
6. Review: bad or suspicious trades may create automatic review cases and contribute to antipattern learning.
7. Analytics: closed trades feed strategy performance and calibration metrics.

## Integration boundaries
- Telegram boundary: UI-only integration through bot API, callbacks, and message rendering.
- Polymarket boundary: market metadata and pricing only. No real order placement in the current version.
- News boundary: RSS and web content collection only. No business logic in fetchers.
- LLM boundary: structured analysis through CometAPI. No trade decisions inside prompts.
- Storage boundary: database stores entities and traces; Redis/queue handles jobs, retries, and deduplication.
- Future execution boundary: a real trading module must be able to consume signal or order intents without changing market, news, LLM, or review modules.

## Recommended document reading order
1. [SYSTEM_ARCHITECTURE.md](./SYSTEM_ARCHITECTURE.md)
2. [DATA_MODEL.md](./DATA_MODEL.md)
3. [STRATEGY_CONFIG.md](./STRATEGY_CONFIG.md)
4. Module docs in `docs/modules/`
5. Infra docs in `docs/infra/`
