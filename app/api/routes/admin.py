from celery import chain
from fastapi import APIRouter

from app.schemas.api import RunPipelineResponse
from app.workers.tasks.pipeline import (
    news_analysis_task,
    news_ingestion_task,
    paper_trade_monitoring_task,
    signal_generation_task,
)

router = APIRouter(prefix="/admin", tags=["admin"])


_PIPELINE_STEPS = [
    "news_ingestion_task",
    "news_analysis_task",
    "signal_generation_task",
    "paper_trade_monitoring_task",
]


@router.post("/run-pipeline", response_model=RunPipelineResponse)
async def run_pipeline() -> RunPipelineResponse:
    """Force a full pipeline run: ingest news → analyze → generate signals →
    open/monitor paper trades. Each task already self-chains and triggers the
    next stage on success, so we kick off the head of the chain via Celery
    canvas to guarantee ordering even if upstream stages produce zero rows.
    """
    pipeline = chain(
        news_ingestion_task.si(),
        news_analysis_task.si(),
        signal_generation_task.si(),
        paper_trade_monitoring_task.si(),
    )
    result = pipeline.apply_async()
    return RunPipelineResponse(
        queued=True,
        chain_id=str(result.id) if result and result.id else None,
        steps=_PIPELINE_STEPS,
    )
