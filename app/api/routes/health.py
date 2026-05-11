from fastapi import APIRouter

from app.schemas.api import HealthResponse

router = APIRouter(prefix="/health", tags=["health"])


@router.get("", response_model=HealthResponse)
async def healthcheck() -> HealthResponse:
    return HealthResponse()

