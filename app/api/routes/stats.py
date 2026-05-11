from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_container, get_session
from app.schemas.api import StatsOut
from app.services.container import ServiceContainer

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("", response_model=StatsOut)
async def get_stats(
    session: AsyncSession = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> StatsOut:
    return await container.analytics_service.get_stats(session=session)

