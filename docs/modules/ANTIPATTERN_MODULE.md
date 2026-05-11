# Antipattern Module

## Module responsibility
Store recurring failure patterns, detect them, link them to signals, and apply strategy-side penalties or warnings.

## Module inputs
- Signal context
- Review history
- News and source metadata
- Strategy config penalty rules

## Module outputs
- Antipattern definitions
- Antipattern matches
- Confidence penalties
- Blocking or downgrade instructions
- User-visible warnings

## Dependencies
- Error review module
- Signal engine
- Strategy config
- Database

## Purpose
Prevent repeated mistakes by turning recurring bad cases into explicit, reusable decision rules.

## Responsibilities
- Store antipattern definitions
- Detect antipatterns
- Link signals to antipatterns
- Apply confidence penalties
- Display warnings

## Possible strategy effects
- Reduce confidence
- Block automatic paper trade
- Require additional confirmation
- Downgrade signal status
- Show warning without blocking

## Example antipatterns
- Single-source bias
- Already priced event
- Breaking news overreaction
- Weak narrative signal
- Weak mapping between event and market wording
- Recycled stale news

## Antipattern definition fields
- Code
- Name
- Description
- Detection logic description
- Penalty action
- Penalty value
- Active flag

## Detection modes
- Rule-based automatic detection from signal context
- Manual attachment by the user
- Review-driven suggestions promoted into formal rules later

## Required interfaces
- `listAntipatterns(filters)`
- `createAntipattern(definition)`
- `updateAntipattern(id, fields)`
- `detectAntipatterns(signalContext)`
- `assignAntipattern(signalId, antipatternId, mode)`

## Reliability rules
- Detection should be deterministic for a given ruleset and input.
- Penalties must be traceable on each affected signal.
- Disabled antipatterns must remain queryable historically.
