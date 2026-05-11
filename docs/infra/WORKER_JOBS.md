# Worker Jobs

## Module responsibility
Define the background jobs that keep markets, news, analyses, signals, paper trades, and analytics up to date.

## Module inputs
- Scheduler triggers
- Queue messages
- Persistent database state
- External provider responses

## Module outputs
- Updated entities
- New queue events
- Logs, retries, and failure states

## Dependencies
- Queue system such as Redis-backed workers
- Database
- External integrations
- Module services under `docs/modules/`

## Job design rules
- Jobs must be idempotent.
- Jobs must tolerate retries.
- Jobs must log start, finish, duration, and failure reason.
- Jobs should use deduplication keys where repeated scheduling is possible.
- Long-running work should be split into smaller steps when practical.

## Jobs

### Market refresh
Trigger schedule:
- Periodic, for example every 5 to 15 minutes

Inputs:
- Polymarket API

Outputs:
- New or updated `markets`

Failure handling:
- Retry transient failures
- Mark sync attempt failure in logs
- Do not delete existing markets on temporary upstream failure

### Market snapshot updates
Trigger schedule:
- Frequent periodic polling for active markets

Inputs:
- Active market list
- Polymarket price endpoints

Outputs:
- New `market_snapshots`

Failure handling:
- Retry with backoff
- Skip bad markets temporarily without stopping the batch

### News ingestion
Trigger schedule:
- Periodic per source or per source group

Inputs:
- Active source registry

Outputs:
- New or updated `news`
- Queue messages for analysis

Failure handling:
- Retry bounded fetch failures
- Mark problematic sources unhealthy
- Preserve previous source data

### News analysis
Trigger schedule:
- Queue-driven on new candidate news items

Inputs:
- `news`
- Candidate markets
- Prompt templates

Outputs:
- `llm_analyses`
- Analysis traces

Failure handling:
- Retry transient CometAPI errors
- Mark permanent failure state for replay
- Store partial trace if pipeline is interrupted

### Signal generation
Trigger schedule:
- Queue-driven on analysis completion or periodic recomputation for active markets

Inputs:
- `market_snapshots`
- `llm_analyses`
- `strategy_configs`
- Antipattern detections

Outputs:
- `signals`
- Optional Telegram notifications
- Optional paper trade queue events

Failure handling:
- Deduplicate by market, evidence set, and strategy version
- Retry safe persistence failures

### Paper trade monitoring
Trigger schedule:
- Frequent periodic polling for open trades

Inputs:
- Open `paper_trades`
- Latest `market_snapshots`
- `strategy_configs`

Outputs:
- Updated trade state
- Closed trades when exit rules fire

Failure handling:
- Idempotent close processing
- Retry transient storage failures

### Auto review generation
Trigger schedule:
- Periodic or event-driven on trade close and outcome changes

Inputs:
- Closed `paper_trades`
- Linked `signals`
- Review rules

Outputs:
- New `error_reviews`
- Optional antipattern suggestions

Failure handling:
- Deduplicate by target and trigger rule
- Log why review creation was skipped

### Analytics updates
Trigger schedule:
- Periodic batch and on-demand refresh

Inputs:
- Signals, trades, reviews, outcomes, antipattern assignments

Outputs:
- Materialized analytics views or caches

Failure handling:
- Rebuild from source-of-truth tables if cache generation fails
- Timestamp all refresh results
