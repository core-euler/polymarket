# Paper Trading Module

## Module responsibility
Create, track, update, and close simulated trades based on eligible signals.

## Module inputs
- Signal objects and eligibility flags
- Market snapshots
- Strategy configuration
- User manual actions

## Module outputs
- Virtual trade records
- Trade lifecycle state transitions
- Unrealized and realized PnL
- Trade-close reasons

## Dependencies
- Signal engine
- Market data module
- Strategy config
- Database
- Scheduler or worker layer

## Hard boundary
This module must be replaceable later by a real execution engine. It should not embed assumptions that only work for simulated trades.

## Responsibilities
- Create virtual trades
- Track virtual positions
- Update virtual PnL
- Close virtual trades
- Store the trade lifecycle

## Entry rules
- Support manual entry from a signal card.
- Support automatic entry for eligible signals when enabled by strategy config.
- Record entry direction, size, price, time, and open reason.
- Prevent duplicate opens for the same signal when configured.

## Exit rules
- Close on time limit.
- Close on take-profit threshold.
- Close on stop-loss threshold.
- Close on signal invalidation.
- Close on market close or expiry.
- Close manually on user request.

## Position sizing
- Default size may be static or depend on confidence and risk rules.
- Sizing logic must be versioned through strategy config.
- The chosen size must be stored on the trade and never recomputed retroactively.

## Trade state transitions
- `pending`
- `open`
- `closing`
- `closed`
- `canceled`

Transitions should be explicit and logged.

## Required trade fields
- Signal ID
- Market ID
- Direction
- Entry price
- Position size
- Open time
- Open reason
- Status
- Strategy version
- Exit price when closed
- Close time when closed
- Close reason when closed
- Realized PnL when closed

## Required interfaces
- `openPaperTrade(signalId, mode)`
- `updateOpenTrades()`
- `closePaperTrade(tradeId, reason)`
- `getPaperTrade(tradeId)`
- `listPaperTrades(filters)`

## Reliability rules
- Monitoring jobs must be idempotent.
- Exit processing must tolerate repeated execution without double close.
- Persist both the entry snapshot and the exit snapshot for audit.
