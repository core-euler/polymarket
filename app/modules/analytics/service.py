from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ErrorReview, PaperTrade, Signal, SignalAntipattern


class AnalyticsModule:
    async def refresh_aggregates(self, session: AsyncSession) -> int:
        signals = int(await session.scalar(select(func.count()).select_from(Signal)) or 0)
        trades = int(await session.scalar(select(func.count()).select_from(PaperTrade)) or 0)
        reviews = int(await session.scalar(select(func.count()).select_from(ErrorReview)) or 0)
        antipattern_links = int(await session.scalar(select(func.count()).select_from(SignalAntipattern)) or 0)
        _closed_wins = int(
            await session.scalar(
                select(func.count())
                .select_from(PaperTrade)
                .where(PaperTrade.status == "closed", PaperTrade.realized_pnl > 0)
            )
            or 0
        )
        _closed_total = int(
            await session.scalar(
                select(func.count()).select_from(PaperTrade).where(PaperTrade.status == "closed")
            )
            or 0
        )
        return signals + trades + reviews + antipattern_links
