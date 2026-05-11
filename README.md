# Polymarket Assistant (Aiogram + FastAPI + Postgres + Redis + Celery)

Initial implementation scaffold is aligned to project docs in `docs/`.

## Stack
- Telegram bot: `Aiogram 3`
- Backend API: `FastAPI`
- DB: `Postgres` via `SQLAlchemy async`
- Queue and workers: `Redis + Celery`

## Quick start (one command)
1. Copy env:
```bash
cp .env.example .env
```
2. Put your real values in `.env`:
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_ALLOWED_USER_IDS`
- optional: `COMET_API_KEY`, `COMET_MODEL_DEFAULT`
3. Start everything:
```bash
docker compose up --build
```

What happens automatically:
- Postgres + Redis start
- API starts and creates tables
- `seed` bootstrap runs once:
- creates strategy/sources/account
- runs initial market/news/analysis/signal pipeline
- if APIs are unavailable (non-production), adds demo data so bot is not empty
- Bot + worker + beat start after successful bootstrap

## Local setup (manual mode)
1. Copy env:
```bash
cp .env.example .env
```
2. Start infra:
```bash
docker compose up -d
```
3. Install dependencies:
```bash
python3 -m pip install -e ".[dev]"
```
4. Run API:
```bash
make run-api
```
5. Run bot:
```bash
make run-bot
```
6. Run worker and beat:
```bash
make run-worker
make run-beat
```

## Current implementation
- FastAPI app with base routes:
- `GET /api/v1/health`
- `GET /api/v1/markets`
- `GET /api/v1/signals`
- `GET /api/v1/paper-trades`
- `GET /api/v1/stats`
- Aiogram inline menu with screens:
- `Signals`, `Markets`, `Paper Trades`, `Statistics`
- placeholders for:
- `Errors Review`, `Antipatterns`, `Settings`
- SQLAlchemy schema aligned with `docs/DATA_MODEL.md` baseline.
- Implemented modules:
- market sync + snapshots
- news ingestion + dedup
- LLM analysis pipeline for pending news
- signal generation with idempotency
- paper trading open/monitor/close basics
- auto-review + antipattern assignment
- analytics refresh aggregation
- Celery scheduled jobs:
- `market_refresh_task`
- `market_snapshot_task`
- `news_ingestion_task`
- `news_analysis_task`
- `signal_generation_task`
- `paper_trade_monitoring_task`
- `auto_review_task`
- `analytics_refresh_task`

## Useful checks
```bash
docker compose logs -f seed
docker compose logs -f bot
curl http://localhost:8000/api/v1/health
```

## Next phase
- expand LLM analyzer from null/fake outputs to real structured Comet parsing
- implement richer strategy config usage (thresholds, suppress/block rules, sizing)
- add end-to-end integration tests with Postgres + Redis containers
