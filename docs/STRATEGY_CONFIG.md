# Strategy Config

## Module responsibility
Define the configurable parameters that control signal scoring, risk filtering, antipattern effects, and paper trading behavior.

## Module inputs
- Market behavior assumptions
- Signal engine requirements
- Paper trading requirements
- Review and antipattern feedback

## Module outputs
- Versioned strategy profiles
- Thresholds and rule definitions used by the signal engine and paper trading module
- Audit-ready configuration history

## Dependencies
- [SYSTEM_ARCHITECTURE.md](./SYSTEM_ARCHITECTURE.md)
- [DATA_MODEL.md](./DATA_MODEL.md)
- [SIGNAL_ENGINE.md](./modules/SIGNAL_ENGINE.md)
- [PAPER_TRADING_MODULE.md](./modules/PAPER_TRADING_MODULE.md)
- [ANTIPATTERN_MODULE.md](./modules/ANTIPATTERN_MODULE.md)

## Configuration principles
- Treat configuration as versioned data, not hard-coded constants.
- Every signal and paper trade must store the exact strategy version used.
- Make parameters editable through controlled UI or config management.
- Log every config change with actor, timestamp, and change reason.

## Strategy parameters

### Signal thresholds
- `minimum_confidence`
- `minimum_edge`
- `minimum_liquidity`
- `maximum_news_age_minutes`
- `minimum_confirming_sources`
- `minimum_market_lifetime_remaining`

### Risk controls
- `blacklisted_topics`
- `blacklisted_markets`
- `cooldown_window_minutes`
- `max_active_paper_trades`
- `max_new_trades_per_hour`
- `single_source_penalty_enabled`
- `stale_news_penalty_enabled`

### Antipattern effects
- `confidence_penalty_by_antipattern`
- `block_auto_paper_trade_by_antipattern`
- `require_extra_confirmation_by_antipattern`
- `downgrade_status_by_antipattern`

### Paper trading rules
- `auto_paper_trade_enabled`
- `manual_paper_trade_enabled`
- `default_position_size`
- `position_size_by_confidence`
- `take_profit_rule`
- `stop_loss_rule`
- `max_holding_duration_minutes`
- `close_on_signal_invalidation`
- `close_on_market_close`

## Versioning model
- A strategy profile consists of a stable profile name and a monotonically increasing version.
- Any change to scoring, risk, antipattern, or paper trade behavior creates a new version.
- Old versions remain queryable and immutable.
- One active version per profile should be marked for runtime selection.

## Change management
- Changes may originate from Telegram settings UI, admin tooling, or environment bootstrap.
- Each change should record:
- `changed_by`
- `changed_at`
- `previous_version`
- `new_version`
- `change_reason`

## Runtime usage
- The signal engine reads the active strategy profile during evaluation.
- The paper trading module reads the same profile or the version already attached to a signal.
- Long-running trade monitoring should prefer the trade's stored strategy version rather than the latest config.

## Validation rules
- Thresholds must be within safe ranges.
- Penalty rules must not produce impossible values such as confidence below zero.
- Auto-trading rules must not bypass blacklist, liquidity, or antipattern blocks.
- Version activation should be atomic to prevent mixed-rule execution in workers.

## Recommended shape
The persistent config payload should be organized into sections:
- `signal_thresholds`
- `risk_controls`
- `antipattern_rules`
- `paper_trading_rules`
- `metadata`
