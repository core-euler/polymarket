from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "polymarket_assistant",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.workers.tasks.pipeline"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    beat_schedule={
        # Список рынков обновляем раз в 15 минут
        "market-refresh": {
            "task": "app.workers.tasks.pipeline.market_refresh_task",
            "schedule": 900.0,
        },
        # Снапшоты цен — раз в 5 минут
        "market-snapshot-refresh": {
            "task": "app.workers.tasks.pipeline.market_snapshot_task",
            "schedule": 300.0,
        },
        # Новости — раз в 15 минут
        "news-ingestion": {
            "task": "app.workers.tasks.pipeline.news_ingestion_task",
            "schedule": 900.0,
        },
        # LLM-анализ — раз в 2 минуты. Пустые тики дешёвые: если pending news нет,
        # analyze_pending_news сразу возвращает 0. Дренаж очереди — через self-chain
        # внутри таски, а не через частоту beat.
        "news-analysis": {
            "task": "app.workers.tasks.pipeline.news_analysis_task",
            "schedule": 120.0,
        },
        # v5: LLM-трейдер. Событийно дёргается из news_analysis_task при новых
        # анализах; этот beat-тик (раз в 5 мин, в такт снапшотам) ловит
        # триггеры по движению цены. Пустые тики дешёвые: нет «грязных»
        # рынков → run_cycle сразу возвращает 0 без вызова LLM.
        "llm-trader": {
            "task": "app.workers.tasks.pipeline.llm_trader_task",
            "schedule": 300.0,
        },
        # v5: грейдер решений. Раз в 10 минут заполняет цены через 1ч/4ч/24ч
        # и исход рынка в llm_decisions — это измеритель калибровки/edge.
        # Идемпотентен: пишет только в NULL-поля, пустые тики дешёвые.
        "llm-scorer": {
            "task": "app.workers.tasks.pipeline.llm_scorer_task",
            "schedule": 600.0,
        },
        # Авто-review и antipattern — раз в 30 минут
        "auto-review": {
            "task": "app.workers.tasks.pipeline.auto_review_task",
            "schedule": 1800.0,
        },
        # Аналитика — раз в 30 минут
        "analytics-refresh": {
            "task": "app.workers.tasks.pipeline.analytics_refresh_task",
            "schedule": 1800.0,
        },
    },
)
