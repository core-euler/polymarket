from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Antipattern, PaperTrade, Signal, SignalAntipattern


class AntipatternModule:
    async def detect_for_recent_signals(self, session: AsyncSession) -> int:
        code = "HIGH_CONFIDENCE_LOSS"
        antipattern = await session.scalar(select(Antipattern).where(Antipattern.code == code))
        if antipattern is None:
            antipattern = Antipattern(
                code=code,
                name="High Confidence Loss",
                description="High confidence signals that resulted in losing closed trades.",
                detection_logic_description="signal.confidence >= 0.75 and closed trade pnl <= 0",
                penalty_action="reduce_confidence",
                penalty_value=0.2,
                active_flag=True,
            )
            session.add(antipattern)
            await session.flush()

        candidate_signals = list(
            await session.scalars(
                select(Signal)
                .join(PaperTrade, PaperTrade.signal_id == Signal.id)
                .where(
                    Signal.confidence >= 0.75,
                    PaperTrade.status == "closed",
                    PaperTrade.realized_pnl.is_not(None),
                    PaperTrade.realized_pnl <= 0,
                )
                .order_by(Signal.id.asc())
            )
        )

        created = 0
        now = datetime.now(timezone.utc)
        for signal in candidate_signals:
            exists = await session.scalar(
                select(SignalAntipattern.id).where(
                    and_(
                        SignalAntipattern.signal_id == signal.id,
                        SignalAntipattern.antipattern_id == antipattern.id,
                    )
                )
            )
            if exists is not None:
                continue

            link = SignalAntipattern(
                signal_id=signal.id,
                antipattern_id=antipattern.id,
                assignment_mode="auto",
                comment="Assigned by auto-review loss detector",
                created_at=now,
            )
            session.add(link)
            created += 1

        await session.commit()
        return created
