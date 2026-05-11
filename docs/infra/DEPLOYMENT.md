# Deployment

## Module responsibility
Define runtime topology, infrastructure services, configuration, secrets handling, and environment setup for development and production.

## Module inputs
- Application service requirements
- Background worker requirements
- External provider credentials

## Module outputs
- Environment layout
- Required services
- Environment variables and secrets policy
- Deployment expectations for development and production

## Dependencies
- Docker or equivalent container runtime
- Database
- Redis or queue backend
- Telegram bot credentials
- CometAPI credentials

## Service layout
Recommended runtime services:
- API and application service
- Telegram bot process
- Worker process
- Scheduler process
- Database
- Redis or queue service

These may be combined for local development but should remain logically separated.

## Docker setup
- Define separate containers for app, worker, scheduler, database, and Redis.
- Use a shared image for app, worker, and scheduler when the codebase is unified.
- Keep environment-specific values outside images.

## Environment variables
Minimum configuration groups:
- Telegram:
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_ALLOWED_USER_IDS`
- CometAPI:
- `COMET_API_KEY`
- `COMET_MODEL_DEFAULT`
- Market data:
- `POLYMARKET_API_BASE_URL`
- Database:
- `DATABASE_URL`
- Queue:
- `REDIS_URL`
- App behavior:
- `APP_ENV`
- `LOG_LEVEL`
- `DEFAULT_TIMEZONE`

## Secrets management
- Never store secrets in source control.
- Use environment variables or secret manager injection.
- Separate development and production secrets.
- Rotate bot and API keys without code changes.

## Database configuration
- Use a persistent relational database for source-of-truth entities.
- Run schema migrations explicitly as part of deploy or release workflow.
- Back up production data, especially audit-heavy tables such as analyses, signals, trades, and reviews.

## Redis and queue setup
- Use Redis or an equivalent broker for async jobs, retry queues, and deduplication support.
- Configure retry limits and dead-letter handling for failed jobs.

## Worker processes
- Run dedicated worker processes for background jobs.
- Run a scheduler process for cron-like job dispatch.
- Ensure workers can scale independently from the Telegram or API process.

## Development environment
- Prefer a local `docker compose` setup for database and Redis.
- Run app, worker, and scheduler in local dev mode or inside containers.
- Use sandbox-safe fake or test credentials where possible.
- Keep local logging verbose and structured.

## Production environment
- Separate web-facing and worker processes.
- Use monitored persistent services for database and Redis.
- Keep secrets in a managed secret store.
- Enable structured logs and alerting on queue failures, provider failures, and job backlog growth.

## Operational requirements
- Health checks for app, worker, and scheduler
- Structured logs
- Retry and dead-letter policies
- Metrics for queue depth, job failure rate, and external API error rate
- Safe rollout path for strategy config changes
