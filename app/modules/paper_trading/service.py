from __future__ import annotations

from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Market, MarketSnapshot, PaperTrade, Signal, StrategyConfig
from app.db.models.entities import VirtualAccount

_log = structlog.get_logger("paper_trading")
_FAR_FROM_EXPIRY = timedelta(hours=24)


class PaperTradingModule:
    async def _get_account(self, session: AsyncSession) -> VirtualAccount | None:
        return await session.scalar(select(VirtualAccount).order_by(VirtualAccount.id.asc()))

    async def _get_active_strategy(self, session: AsyncSession) -> StrategyConfig | None:
        return await session.scalar(
            select(StrategyConfig)
            .where(StrategyConfig.active_flag.is_(True))
            .order_by(StrategyConfig.version.desc(), StrategyConfig.id.desc())
        )

    async def open_eligible_trades(self, session: AsyncSession) -> int:
        account = await self._get_account(session)
        if account is None:
            return 0

        active_strategy = await self._get_active_strategy(session)
        if active_strategy is None:
            return 0

        eligible_statuses = await self._eligible_signal_statuses(session)
        # Bind paper-trade openings to the currently active strategy. Old signals
        # that came in under a deprecated strategy version stay in the database
        # for audit but never spawn new trades — their pricing/risk filters do
        # not match what we are betting on right now.
        signals = list(
            await session.scalars(
                select(Signal)
                .where(
                    Signal.status.in_(eligible_statuses),
                    Signal.strategy_config_id == active_strategy.id,
                )
                .order_by(Signal.id.asc())
            )
        )
        created = 0

        for signal in signals:
            existing_trade_id = await session.scalar(
                select(PaperTrade.id).where(PaperTrade.signal_id == signal.id)
            )
            if existing_trade_id is not None:
                continue

            # Dedupe by market: at most one OPEN paper trade per market across signals.
            open_trade_for_market = await session.scalar(
                select(PaperTrade.id).where(
                    PaperTrade.market_id == signal.market_id,
                    PaperTrade.status == "open",
                )
            )
            if open_trade_for_market is not None:
                continue

            strategy = await session.scalar(
                select(StrategyConfig).where(StrategyConfig.id == signal.strategy_config_id)
            )
            if strategy is None:
                continue

            rules = strategy.paper_trading_rules_json or {}
            if not bool(rules.get("auto_paper_trade_enabled", True)):
                continue

            size = float(strategy.parameters_json.get("default_position_size", 0.1))

            if account.balance < size:
                break

            entry_price = float(signal.market_probability)
            direction = "YES" if signal.edge >= 0 else "NO"

            trade = PaperTrade(
                signal_id=signal.id,
                market_id=signal.market_id,
                direction=direction,
                entry_price=entry_price,
                position_size=size,
                open_time=datetime.now(timezone.utc),
                status="open",
                open_reason="auto_from_signal",
                strategy_config_id=signal.strategy_config_id,
                strategy_version=signal.strategy_version,
            )
            session.add(trade)
            account.balance -= size
            created += 1

        await session.commit()
        return created

    async def _eligible_signal_statuses(self, session: AsyncSession) -> list[str]:
        """Read configured minimum signal status from the active strategy.

        Defaults to {paper_trade_candidate} for backwards compatibility, but
        strategy.paper_trading_rules_json.eligible_signal_statuses can override
        with e.g. ["paper_trade_candidate", "valid_signal"] to widen entries.
        """
        strategy = await session.scalar(
            select(StrategyConfig)
            .where(StrategyConfig.active_flag.is_(True))
            .order_by(StrategyConfig.version.desc(), StrategyConfig.id.desc())
        )
        default = ["paper_trade_candidate"]
        if strategy is None:
            return default
        rules = strategy.paper_trading_rules_json or {}
        configured = rules.get("eligible_signal_statuses")
        if isinstance(configured, list) and configured:
            return [str(s) for s in configured if isinstance(s, str)]
        return default

    async def monitor_open_trades(self, session: AsyncSession) -> int:
        account = await self._get_account(session)
        # Risk parameters are live: we monitor every open position with the
        # currently-active strategy rules. The trade keeps trade.strategy_config_id
        # as an audit record of opening context, but TP/SL/time/jump rules
        # follow the version we are operating under right now. This protects us
        # when a buggy older strategy created positions we still hold open.
        active_strategy = await self._get_active_strategy(session)

        open_trades = list(
            await session.scalars(
                select(PaperTrade).where(PaperTrade.status == "open").order_by(PaperTrade.id.asc())
            )
        )
        closed = 0
        now = datetime.now(timezone.utc)

        for trade in open_trades:
            strategy = active_strategy
            if strategy is None:
                # Fallback: no active strategy at all — fall back to the trade's
                # own strategy so we are not stuck holding positions forever.
                strategy = await session.scalar(
                    select(StrategyConfig).where(StrategyConfig.id == trade.strategy_config_id)
                )
            market = await session.scalar(select(Market).where(Market.id == trade.market_id))
            recent_snapshots = list(
                await session.scalars(
                    select(MarketSnapshot)
                    .where(MarketSnapshot.market_id == trade.market_id)
                    .order_by(MarketSnapshot.id.desc())
                    .limit(2)
                )
            )
            snapshot = recent_snapshots[0] if recent_snapshots else None
            previous_snapshot = recent_snapshots[1] if len(recent_snapshots) >= 2 else None

            if strategy is None or market is None or snapshot is None:
                continue

            rules = strategy.paper_trading_rules_json or {}
            max_holding_minutes = int(rules.get("max_holding_minutes", 120))
            take_profit_abs = float(rules.get("take_profit_abs", 0.0) or 0.0)
            stop_loss_abs = float(rules.get("stop_loss_abs", 0.0) or 0.0)
            take_profit_pct = float(rules.get("take_profit_pct", 0.0) or 0.0)
            stop_loss_pct = float(rules.get("stop_loss_pct", 0.0) or 0.0)
            max_mark_jump = float(rules.get("max_mark_jump_per_tick", 0.0) or 0.0)

            mark_price = float(
                snapshot.implied_probability or snapshot.last_price or trade.entry_price
            )

            # Skip suspicious tick: a probability jump larger than configured
            # while the market is still far from resolution almost always means
            # bad snapshot data (illiquid book, stale gamma payload, settled
            # field set early). Better to keep the position open and wait for
            # the next tick than to close on a fake mark.
            if max_mark_jump > 0 and previous_snapshot is not None:
                prev_mark = float(
                    previous_snapshot.implied_probability
                    or previous_snapshot.last_price
                    or 0.0
                )
                if prev_mark > 0:
                    expires_at = market.expires_at
                    if expires_at is not None and expires_at.tzinfo is None:
                        expires_at = expires_at.replace(tzinfo=timezone.utc)
                    far_from_expiry = (
                        expires_at is None or (expires_at - now) > _FAR_FROM_EXPIRY
                    )
                    if (
                        far_from_expiry
                        and abs(mark_price - prev_mark) > max_mark_jump
                    ):
                        _log.warning(
                            "monitor.skip_suspicious_jump",
                            trade_id=trade.id,
                            market_id=market.id,
                            prev_mark=prev_mark,
                            new_mark=mark_price,
                            max_jump=max_mark_jump,
                        )
                        continue
            if trade.direction == "YES":
                price_delta = mark_price - trade.entry_price
            else:
                price_delta = trade.entry_price - mark_price
            pnl = price_delta * trade.position_size

            open_time = trade.open_time
            if open_time.tzinfo is None:
                open_time = open_time.replace(tzinfo=timezone.utc)
            elapsed_seconds = (now - open_time).total_seconds()
            time_limit_hit = elapsed_seconds >= max_holding_minutes * 60
            market_inactive = market.status != "active"

            # Absolute thresholds win when configured. They are the right model for
            # probability instruments: 0.10 means "10 percentage points of probability
            # in our favor", regardless of whether entry was 0.07 or 0.55. Relative
            # *_pct are kept as a legacy fallback only when *_abs is unset.
            if take_profit_abs > 0:
                take_profit_hit = price_delta >= take_profit_abs
            elif take_profit_pct > 0:
                entry = trade.entry_price or 1e-9
                take_profit_hit = (price_delta / entry) >= take_profit_pct
            else:
                take_profit_hit = False

            if stop_loss_abs > 0:
                stop_loss_hit = price_delta <= -stop_loss_abs
            elif stop_loss_pct > 0:
                entry = trade.entry_price or 1e-9
                stop_loss_hit = (price_delta / entry) <= -stop_loss_pct
            else:
                stop_loss_hit = False

            if not (time_limit_hit or market_inactive or take_profit_hit or stop_loss_hit):
                continue

            if take_profit_hit:
                close_reason = "take_profit"
            elif stop_loss_hit:
                close_reason = "stop_loss"
            elif market_inactive:
                close_reason = "market_inactive"
            else:
                close_reason = "time_limit"

            trade.status = "closed"
            trade.exit_price = mark_price
            trade.close_time = now
            trade.realized_pnl = pnl
            trade.close_reason = close_reason

            if account is not None:
                account.balance += trade.position_size + pnl

            closed += 1

        await session.commit()
        return closed
