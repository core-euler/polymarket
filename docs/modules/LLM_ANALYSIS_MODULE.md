# LLM Analysis Module

## Module responsibility
Use CometAPI to perform structured analysis of normalized news against candidate markets.

## Module inputs
- Normalized news records
- Candidate market context
- Prompt template versions
- Model routing rules

## Module outputs
- Structured relevance decisions
- Extracted facts and entities
- Event-to-market mapping
- Impact direction and strength
- Confidence estimates
- Contradiction and uncertainty notes
- Human-readable summary
- Persisted analysis traces

## Dependencies
- CometAPI
- Prompt templates
- Database
- Market context lookups

## Hard boundary
This module does not:
- Make trade decisions
- Assign signal status
- Open paper trades
- Apply strategy thresholds

## Analysis pipeline
1. News input
2. Relevance check
3. Fact extraction
4. Entity extraction
5. Event analysis
6. Event-to-market mapping
7. Impact scoring
8. Confidence estimation
9. Contradiction detection
10. Structured result persistence
11. Human-readable summary generation

## Pipeline stages

### Relevance check
- Decide whether the news can affect a specific market.
- Return structured relevance instead of free text.

### Fact extraction
- Extract claims, dates, quantities, actors, and concrete developments.

### Entity extraction
- Extract people, organizations, places, dates, and numerical indicators.

### Event analysis
- Identify the event type and event timing.
- Distinguish fact from narrative or speculation.

### Event-to-market mapping
- Explain why the event matters or does not matter to the market wording.

### Impact scoring
- Estimate direction toward `YES`, `NO`, or `NEUTRAL`.
- Estimate impact strength.

### Confidence estimation
- Evaluate source quality, evidence strength, recency, and contradictions.

### Contradiction detection
- Note conflicting sources, uncertain facts, and ambiguous timing.

## Structured result contract
Each analysis should include:
- Market ID
- News ID
- Model name
- Prompt template version
- Relevance
- Event time
- Facts
- Entities
- Impact direction
- Impact strength
- Confidence
- Uncertainties
- Contradictions
- Summary
- Trace metadata

## Prompting rules
- Avoid single giant prompts that perform every task at once.
- Keep stage outputs machine-readable.
- Separate prompt templates by stage and version them explicitly.
- Make model swaps possible without changing business logic.

## Required interfaces
- `analyzeNewsForMarket(newsId, marketId)`
- `runRelevanceCheck(newsId, marketId)`
- `runFactExtraction(newsId)`
- `runImpactScoring(newsId, marketId, facts)`
- `storeAnalysis(result)`
- `getAnalysesForNews(newsId)`

## Reliability rules
- Retry transient CometAPI failures.
- Mark failed analyses explicitly for replay.
- Store partial traces when a multi-stage pipeline fails mid-run.
- Keep analysis records immutable after creation.
