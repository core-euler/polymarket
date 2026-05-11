from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ErrorReview, PaperTrade, Signal


class ErrorReviewModule:
    async def create_auto_reviews(self, session: AsyncSession) -> int:
        trades = list(
            await session.scalars(
                select(PaperTrade).where(
                    PaperTrade.status == "closed",
                    PaperTrade.realized_pnl.is_not(None),
                    PaperTrade.realized_pnl <= 0,
                )
            )
        )
        created = 0
        now = datetime.now(timezone.utc)

        for trade in trades:
            exists = await session.scalar(
                select(ErrorReview.id).where(
                    ErrorReview.review_target_type == "paper_trade",
                    ErrorReview.review_target_id == trade.id,
                    ErrorReview.origin == "auto",
                )
            )
            if exists is not None:
                continue

            signal = await session.scalar(select(Signal).where(Signal.id == trade.signal_id))
            confidence = float(signal.confidence) if signal is not None else 0.0

            if confidence >= 0.7:
                error_type = "high_confidence_loss"
                severity = "high"
            else:
                error_type = "negative_pnl"
                severity = "medium"

            review = ErrorReview(
                review_target_type="paper_trade",
                review_target_id=trade.id,
                error_type=error_type,
                severity=severity,
                origin="auto",
                comment="Auto review generated from closed losing paper trade",
                created_by_user_id=None,
                created_at=now,
            )
            session.add(review)
            created += 1

        await session.commit()
        return created
