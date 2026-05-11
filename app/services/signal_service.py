from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Signal


class SignalService:
    async def list_signals(self, session: AsyncSession, limit: int = 50) -> list[Signal]:
        stmt = select(Signal).order_by(Signal.id.desc()).limit(limit)
        rows = await session.scalars(stmt)
        return list(rows)

