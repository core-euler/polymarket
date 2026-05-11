from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import PaperTrade, Signal
from app.db.models.entities import StrategyConfig, VirtualAccount
from app.schemas.api import PastStrategySummary, StatsOut

# Statuses that represent signals actually flowing into the trading funnel.
# Excludes suppressed_by_risk, blocked_by_antipattern, informational, weak.
_ACTIVE_SIGNAL_STATUSES = ("paper_trade_candidate", "valid_signal")


class AnalyticsService:
    async def get_stats(self, session: AsyncSession) -> StatsOut:
        active = await session.scalar(
            select(StrategyConfig)
            .where(StrategyConfig.active_flag.is_(True))
            .order_by(StrategyConfig.version.desc())
        )
        active_id = active.id if active else None
        active_version = active.version if active else None

        account = await session.scalar(select(VirtualAccount).order_by(VirtualAccount.id.asc()))
        balance = float(account.balance) if account else 0.0
        initial_balance = float(account.initial_balance) if account else 0.0

        if active_id is None:
            return StatsOut(balance=balance, equity=balance, initial_balance=initial_balance)

        total_paper_trades = await session.scalar(
            select(func.count())
            .select_from(PaperTrade)
            .where(PaperTrade.strategy_config_id == active_id)
        ) or 0
        open_trades = await session.scalar(
            select(func.count())
            .select_from(PaperTrade)
            .where(PaperTrade.strategy_config_id == active_id, PaperTrade.status == "open")
        ) or 0
        closed_trades = await session.scalar(
            select(func.count())
            .select_from(PaperTrade)
            .where(PaperTrade.strategy_config_id == active_id, PaperTrade.status == "closed")
        ) or 0
        winning_closed = await session.scalar(
            select(func.count())
            .select_from(PaperTrade)
            .where(
                PaperTrade.strategy_config_id == active_id,
                PaperTrade.status == "closed",
                PaperTrade.realized_pnl > 0,
            )
        ) or 0
        total_pnl = await session.scalar(
            select(func.sum(PaperTrade.realized_pnl)).where(
                PaperTrade.strategy_config_id == active_id, PaperTrade.status == "closed"
            )
        ) or 0.0
        avg_pnl = await session.scalar(
            select(func.avg(PaperTrade.realized_pnl)).where(
                PaperTrade.strategy_config_id == active_id, PaperTrade.status == "closed"
            )
        ) or 0.0
        best_pnl = await session.scalar(
            select(func.max(PaperTrade.realized_pnl)).where(
                PaperTrade.strategy_config_id == active_id, PaperTrade.status == "closed"
            )
        ) or 0.0
        worst_pnl = await session.scalar(
            select(func.min(PaperTrade.realized_pnl)).where(
                PaperTrade.strategy_config_id == active_id, PaperTrade.status == "closed"
            )
        ) or 0.0
        locked_in_open = await session.scalar(
            select(func.sum(PaperTrade.position_size)).where(
                PaperTrade.strategy_config_id == active_id, PaperTrade.status == "open"
            )
        ) or 0.0

        active_signals_count = await session.scalar(
            select(func.count())
            .select_from(Signal)
            .where(
                Signal.strategy_config_id == active_id,
                Signal.status.in_(_ACTIVE_SIGNAL_STATUSES),
            )
        ) or 0
        total_signals = await session.scalar(
            select(func.count()).select_from(Signal).where(Signal.strategy_config_id == active_id)
        ) or 0

        past_rows = (
            await session.execute(
                select(
                    StrategyConfig.version,
                    func.count(PaperTrade.id),
                    func.coalesce(func.sum(PaperTrade.realized_pnl), 0.0),
                )
                .join(PaperTrade, PaperTrade.strategy_config_id == StrategyConfig.id)
                .where(
                    StrategyConfig.id != active_id,
                    PaperTrade.status == "closed",
                )
                .group_by(StrategyConfig.version)
                .order_by(StrategyConfig.version.asc())
            )
        ).all()
        past_strategies = [
            PastStrategySummary(
                version=int(version),
                closed_trades=int(count),
                total_pnl=float(pnl_sum),
            )
            for version, count, pnl_sum in past_rows
        ]

        winrate = float(winning_closed / closed_trades) if closed_trades else 0.0
        equity = balance + float(locked_in_open or 0.0)
        return StatsOut(
            active_strategy_version=active_version,
            total_signals=int(total_signals),
            total_paper_trades=int(total_paper_trades),
            open_paper_trades=int(open_trades),
            closed_paper_trades=int(closed_trades),
            winrate=winrate,
            balance=balance,
            locked_in_open=float(locked_in_open or 0.0),
            equity=equity,
            initial_balance=initial_balance,
            total_pnl=float(total_pnl),
            avg_pnl=float(avg_pnl or 0.0),
            best_pnl=float(best_pnl or 0.0),
            worst_pnl=float(worst_pnl or 0.0),
            active_signals_count=int(active_signals_count),
            past_strategies=past_strategies,
        )
