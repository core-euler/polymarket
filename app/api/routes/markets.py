from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_container, get_session
from app.schemas.api import MarketOut
from app.services.container import ServiceContainer

router = APIRouter(prefix="/markets", tags=["markets"])


@router.get("", response_model=list[MarketOut])
async def list_markets(
    limit: int = 50,
    session: AsyncSession = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> list[MarketOut]:
    items = await container.market_service.list_markets(session=session, limit=limit)
    return [
        MarketOut(
            id=item.id,
            polymarket_id=item.polymarket_id,
            title=item.title,
            topic=item.topic,
            status=item.status,
            watchlist_flag=item.watchlist_flag,
            blacklist_flag=item.blacklist_flag,
            archived_flag=item.archived_flag,
        )
        for item in items
    ]

