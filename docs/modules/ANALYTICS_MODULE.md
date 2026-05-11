# Analytics Module

## Module responsibility
Measure system performance and support strategy calibration, source evaluation, and learning from outcomes.

## Module inputs
- Signals
- Paper trades
- Error reviews
- Antipattern assignments
- Market outcomes
- Source metadata

## Module outputs
- Signal statistics
- Paper trade statistics
- Calibration reports
- Source performance views
- Antipattern statistics
- User-facing analytics summaries

## Dependencies
- Database
- Signal engine outputs
- Paper trading outputs
- Review and antipattern data

## Responsibilities
- Signal statistics
- Paper trade statistics
- Win rate calculation
- Edge distribution analysis
- Confidence calibration
- Source performance analysis
- Antipattern statistics

## Core metrics
- Signal count by status
- Average edge
- Average confidence
- Trade win rate
- Average realized PnL
- Trade duration distribution
- Calibration by confidence bucket
- Source quality by downstream outcome
- Antipattern frequency and impact

## Required slices
- By topic
- By market
- By news type
- By source
- By confidence range
- By trade holding time
- By antipattern presence
- By manual review category

## Calibration purpose
The system must measure whether predicted probabilities align with realized outcomes, not only whether paper trading produced profit.

## Required interfaces
- `getSignalStats(filters)`
- `getTradeStats(filters)`
- `getCalibrationReport(filters)`
- `getSourcePerformance(filters)`
- `getAntipatternStats(filters)`

## Reliability rules
- Analytics jobs should be recomputable from source-of-truth tables.
- Derived metrics must be timestamped or versioned if cached.
- User-facing analytics should clearly distinguish realized metrics from in-flight estimates.
