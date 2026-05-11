from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_container, get_session
from app.schemas.api import PaperTradeOut
from app.services.container import ServiceContainer

router = APIRouter(prefix="/paper-trades", tags=["paper-trades"])


@router.get("", response_model=list[PaperTradeOut])
async def list_paper_trades(
    limit: int = 50,
    session: AsyncSession = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> list[PaperTradeOut]:
    items = await container.paper_trade_service.list_trades(session=session, limit=limit)
    return [
        PaperTradeOut(
            id=item.id,
            signal_id=item.signal_id,
            market_id=item.market_id,
            direction=item.direction,
            entry_price=item.entry_price,
            position_size=item.position_size,
            status=item.status,
            open_time=item.open_time,
        )
        for item in items
    ]

