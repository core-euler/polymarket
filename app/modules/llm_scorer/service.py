"""v5 scorer — fills the grading columns on llm_decisions.

This is the measurement instrument for LLM-as-trader. Without it we only have
PnL, which is exactly what disguised the decay-harvest artifact as "edge" in
v1-v4. The scorer records, for every decision, where the market price went at
+1h/+4h/+24h, and (best-effort) the resolved outcome. Interpretation lives in
report.py; this module only captures ground truth.

It changes no schema (the columns already exist) and writes only to NULL
grading fields, so it is idempotent and safe to run on every beat tick.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.entities import LLMDecision, Market, MarketSnapshot

# Reuse the trader's price basis so horizon prices are on the same scale as
# price_at_decision (implied_probability, falling back to last_price).
from app.modules.llm_trader.service import _snapshot_price

# (column, hours-after-decision) the scorer fills.
_HORIZONS: tuple[tuple[str, float], ...] = (
    ("price_t1h", 1.0),
    ("price_t4h", 4.0),
    ("price_t24h", 24.0),
)


def _as_aware(dt: datetime) -> datetime:
    """Normalize to tz-aware UTC. SQLite (tests) can hand back naive datetimes;
    Postgres returns aware ones. Normalizing keeps arithmetic/comparison sane on
    both."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


class LLMScorerModule:
    def __init__(
        self,
        *,
        horizon_tolerance_hours: float = 2.0,
        resolve_yes_threshold: float = 0.85,
        resolve_no_threshold: float = 0.15,
    ) -> None:
        # How far a snapshot may be from the exact horizon timestamp and still
        # count. Snapshots land ~every 5 min, so 2h is generous slack for gaps.
        self.horizon_tolerance = timedelta(hours=horizon_tolerance_hours)
        # Snapshots reject prices in [0,0.02]u[0.98,1] as garbage, so a resolved
        # market's last *stored* price sits just inside the boundary. These soft
        # thresholds read direction from it; anything ambiguous stays NULL.
        self.resolve_yes_threshold = resolve_yes_threshold
        self.resolve_no_threshold = resolve_no_threshold

    async def run_cycle(self, session: AsyncSession) -> dict[str, int]:
        now = datetime.now(timezone.utc)
        prices = await self._grade_prices(session, now)
        resolutions = await self._grade_resolutions(session)
        await session.commit()
        return {"prices": prices, "resolutions": resolutions}

    async def _grade_prices(self, session: AsyncSession, now: datetime) -> int:
        filled = 0
        for column, hours in _HORIZONS:
            cutoff = now - timedelta(hours=hours)
            rows = await session.scalars(
                select(LLMDecision).where(
                    getattr(LLMDecision, column).is_(None),
                    LLMDecision.price_at_decision.is_not(None),
                    LLMDecision.decided_at <= cutoff,
                )
            )
            for decision in rows:
                target = _as_aware(decision.decided_at) + timedelta(hours=hours)
                price = await self._price_at(session, decision.market_id, target)
                if price is not None:
                    setattr(decision, column, price)
                    filled += 1
        return filled

    async def _price_at(
        self, session: AsyncSession, market_id: int, target: datetime
    ) -> float | None:
        """Snapshot price nearest to `target`, within tolerance. Considers the
        first snapshot at/after target and the last one before it, picks the
        closer."""
        after = await session.scalar(
            select(MarketSnapshot)
            .where(
                MarketSnapshot.market_id == market_id,
                MarketSnapshot.captured_at >= target,
            )
            .order_by(MarketSnapshot.captured_at.asc())
            .limit(1)
        )
        before = await session.scalar(
            select(MarketSnapshot)
            .where(
                MarketSnapshot.market_id == market_id,
                MarketSnapshot.captured_at < target,
            )
            .order_by(MarketSnapshot.captured_at.desc())
            .limit(1)
        )
        best: MarketSnapshot | None = None
        best_dist: timedelta | None = None
        for snap in (after, before):
            if snap is None:
                continue
            dist = abs(_as_aware(snap.captured_at) - target)
            if dist <= self.horizon_tolerance and (best_dist is None or dist < best_dist):
                best = snap
                best_dist = dist
        if best is None:
            return None
        return _snapshot_price(best)

    async def _grade_resolutions(self, session: AsyncSession) -> int:
        rows = await session.scalars(
            select(LLMDecision)
            .join(Market, Market.id == LLMDecision.market_id)
            .where(
                LLMDecision.resolved_outcome.is_(None),
                Market.status == "closed",
            )
        )
        filled = 0
        for decision in rows:
            outcome = await self._infer_outcome(session, decision.market_id)
            if outcome is not None:
                decision.resolved_outcome = outcome
                filled += 1
        return filled

    async def _infer_outcome(self, session: AsyncSession, market_id: int) -> str | None:
        last = await session.scalar(
            select(MarketSnapshot)
            .where(MarketSnapshot.market_id == market_id)
            .order_by(MarketSnapshot.captured_at.desc())
            .limit(1)
        )
        if last is None:
            return None
        price = _snapshot_price(last)
        if price >= self.resolve_yes_threshold:
            return "YES"
        if price <= self.resolve_no_threshold:
            return "NO"
        return None
