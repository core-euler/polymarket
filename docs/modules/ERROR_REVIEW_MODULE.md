# Error Review Module

## Module responsibility
Capture, classify, and analyze mistakes, suspicious outcomes, and failed predictions.

## Module inputs
- Signals
- Paper trades
- Market outcomes
- News and source metadata
- Manual user review actions

## Module outputs
- Error review records
- Error classifications
- Review statistics
- Feedback inputs for analytics and antipatterns

## Dependencies
- Signal engine
- Paper trading module
- News ingestion metadata
- Analytics module
- Database

## Responsibilities
- Automatic error detection
- Manual error tagging
- Error classification
- Error history
- Error statistics

## Automatic review triggers
- High confidence with bad outcome
- Large edge with negative result
- Single weak source used
- Conflicting sources detected
- Stale news used in a decision
- Low liquidity distortion
- Unconfirmed signal used for trade entry

## Manual review categories
- Already priced in
- Weak source
- Wrong market mapping
- Liquidity noise
- Narrative bias
- Stale news
- Overreaction to breaking news
- False urgency
- Other

## Severity model
- `low`
- `medium`
- `high`
- `critical`

## Review workflow
1. Detect or receive a review trigger.
2. Create an initial review record with target entity and evidence.
3. Allow the user to classify or reclassify the issue.
4. Link the review to sources, news, signal, trade, and optional antipattern.
5. Feed aggregated review outcomes into analytics.

## Required interfaces
- `createAutoReview(target, reason)`
- `createManualReview(target, errorType, comment)`
- `updateReview(reviewId, fields)`
- `listReviews(filters)`
- `getReview(reviewId)`

## Reliability rules
- Reviews should be additive and auditable.
- Automatic reviews must avoid duplicate creation for the same trigger and target.
- Manual review must never overwrite original system evidence.
