from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import PaperTrade


class PaperTradeService:
    async def list_trades(self, session: AsyncSession, limit: int = 50) -> list[PaperTrade]:
        stmt = select(PaperTrade).order_by(PaperTrade.id.desc()).limit(limit)
        rows = await session.scalars(stmt)
        return list(rows)

