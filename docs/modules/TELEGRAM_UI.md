# Telegram UI Module

## Module responsibility
Render the Telegram bot interface and handle user interaction through inline menus, callbacks, pagination, and navigation. This module must not contain business logic.

## Module inputs
- Signal summaries and details
- Market summaries and details
- Paper trade summaries and details
- Error review records
- Antipattern records
- Strategy settings and analytics summaries
- User identity and access status

## Module outputs
- Telegram messages and inline keyboards
- Callback events translated into backend service calls
- UI navigation state

## Dependencies
- Backend application services only
- Telegram Bot API

## Hard boundary
The Telegram UI module must not:
- Score signals
- Compute edge or confidence
- Fetch Polymarket directly
- Perform LLM analysis
- Decide trade entry or exit

## Main screens

### Main menu
Shows top-level navigation to:
- Signals
- Markets
- Paper trades
- Errors and review
- Antipatterns
- Settings
- Statistics

### Signals screen
Displays active and recent signals with filters by status, topic, and time.

### Markets screen
Displays watched, ignored, blacklisted, and archived markets with summary metadata.

### Paper trades screen
Displays active and closed paper trades with status, PnL, and holding duration.

### Errors review screen
Displays automatic and manual review cases with filters by type, severity, source, and date.

### Antipattern database screen
Displays active and inactive antipattern definitions, effects, and linked cases.

### Settings screen
Displays editable strategy thresholds, notification preferences, and source controls.

### Statistics screen
Displays signal performance, trade performance, calibration, and source quality summaries.

## Message layouts

### Signal card
Required fields:
- Market title
- Market question
- Market probability
- Model probability
- Edge
- Confidence
- Short explanation
- Number of sources
- Antipattern warnings
- Signal status

Actions:
- Details
- Sources
- Create paper trade
- Mark error
- Add antipattern
- Ignore market
- Back

### Paper trade card
Required fields:
- Market
- Direction
- Entry price
- Current status
- Current PnL
- Holding time
- Open reason

Actions:
- Details
- Close manually
- Mark error
- Link antipattern
- Back

### Error card
Required fields:
- Linked market or trade
- Error type
- Severity
- Origin
- Date
- Short description

Actions:
- Details
- Change type
- Add comment
- Link antipattern
- Back

### Antipattern card
Required fields:
- Name
- Description
- Strategy effect
- Trigger count
- Active status

Actions:
- Enable or disable
- Edit effect
- View linked cases
- Back

## Inline keyboard structure
- Use compact rows of 1 to 3 buttons.
- Keep destructive or state-changing actions on separate rows.
- Include a `Back` button on every non-root screen.
- Include pagination buttons when lists exceed a page size.
- Include a `Refresh` button only for safe idempotent views.

## Navigation flow
- Use a menu stack per user session.
- Keep callbacks stateless where possible by using identifiers in the payload.
- Preserve the previous list view and page when returning from a detail view.
- Expired callbacks must show a safe refresh or retry message.

## Pagination rules
- Use consistent page sizes per screen type.
- Include `Previous` and `Next` controls only when more pages exist.
- Keep filter state stable across pagination.
- Reject page numbers outside current bounds and fall back to the nearest valid page.

## Callback handling
- Validate access rights before every action.
- Parse callback payload into action, entity type, entity ID, and optional page/filter tokens.
- Route callbacks to application services.
- Always handle repeated clicks idempotently.
- Return a user-friendly fallback for stale, duplicate, or already-completed actions.

## UI state management
- Track current screen, entity context, page, filter state, and pending confirmation state.
- Keep state minimal and reconstructable from callback payload plus backend lookups.
- Require confirmation for actions such as manual trade close, blacklist updates, or destructive config changes.

## Service interfaces expected by UI
- `listSignals`
- `getSignal`
- `listMarkets`
- `getMarket`
- `listPaperTrades`
- `getPaperTrade`
- `listReviews`
- `createReview`
- `listAntipatterns`
- `linkAntipattern`
- `getSettings`
- `updateSettings`
- `getStatistics`
