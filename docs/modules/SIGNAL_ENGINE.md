# Signal Engine

## Module responsibility
Combine market state, normalized news context, LLM analysis, strategy configuration, and antipattern penalties into decision-ready signals.

## Module inputs
- Market data
- Market snapshot baseline
- LLM analysis results
- News metadata
- Strategy configuration
- Antipattern detections

## Module outputs
- Signal objects
- Signal statuses
- Risk flags
- Paper trade eligibility decisions

## Dependencies
- Market data module
- LLM analysis module
- News ingestion metadata
- Strategy config
- Antipattern module
- Database

## Responsibilities
- Signal scoring
- Edge calculation
- Confidence weighting
- Risk filtering
- Antipattern penalties
- Signal classification

## Signal status set
- `informational`
- `weak_signal`
- `valid_signal`
- `paper_trade_candidate`
- `suppressed_by_risk`
- `blocked_by_antipattern`
- `ignored_manually`

## Decision flow
1. Load the current market snapshot.
2. Load recent relevant analyses and linked news metadata.
3. Estimate model probability from structured analysis evidence.
4. Compare model probability with market probability to compute edge.
5. Apply confidence weighting and source-quality adjustments.
6. Apply freshness, liquidity, blacklist, and cooldown filters.
7. Apply antipattern penalties and block rules.
8. Classify the signal and attach risk flags.
9. Persist the signal with full traceable provenance.

## Input factors
- Market implied probability
- Model probability estimate
- Edge
- Confidence
- News freshness
- Source trust score
- Source count and confirmation depth
- Liquidity
- Topic or market blacklist state
- Antipattern matches

## Output contract
Every signal should include:
- Market ID
- Market snapshot ID
- Linked news items
- Linked LLM analyses
- Market probability
- Model probability
- Edge
- Confidence
- Status
- Explanation
- Risk flags
- Strategy config version
- Created time

## Paper trade eligibility
The signal engine may produce:
- `eligible_for_manual_paper_trade`
- `eligible_for_auto_paper_trade`
- `not_eligible`

The paper trading module consumes this output but owns trade creation itself.

## Required interfaces
- `evaluateSignalCandidate(marketId, analysisIds)`
- `calculateModelProbability(context)`
- `applyRiskFilters(candidate, strategyConfig)`
- `classifySignal(candidate)`
- `storeSignal(signal)`

## Reliability rules
- Prevent duplicate signals for the same evidence set and strategy version.
- Keep the original explanation and scores even if later information changes.
- Store enough inputs to replay the decision path.
