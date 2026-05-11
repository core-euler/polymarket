from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_container, get_session
from app.schemas.api import SignalOut
from app.services.container import ServiceContainer

router = APIRouter(prefix="/signals", tags=["signals"])


@router.get("", response_model=list[SignalOut])
async def list_signals(
    limit: int = 50,
    session: AsyncSession = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> list[SignalOut]:
    items = await container.signal_service.list_signals(session=session, limit=limit)
    return [
        SignalOut(
            id=item.id,
            market_id=item.market_id,
            market_probability=item.market_probability,
            model_probability=item.model_probability,
            edge=item.edge,
            confidence=item.confidence,
            status=item.status,
            explanation=item.explanation,
            created_at=item.created_at,
        )
        for item in items
    ]

