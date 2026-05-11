from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Market


class MarketService:
    async def list_markets(self, session: AsyncSession, limit: int = 50) -> list[Market]:
        stmt = select(Market).order_by(Market.id.desc()).limit(limit)
        rows = await session.scalars(stmt)
        return list(rows)

