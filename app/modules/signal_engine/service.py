from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import LLMAnalysis, Market, MarketSnapshot, News, Signal, StrategyConfig


class SignalEngineModule:
    async def generate_signals(self, session: AsyncSession) -> int:
        strategy = await session.scalar(
            select(StrategyConfig)
            .where(StrategyConfig.active_flag.is_(True))
            .order_by(StrategyConfig.version.desc(), StrategyConfig.id.desc())
        )
        if strategy is None:
            return 0

        markets = list(
            await session.scalars(
                select(Market).where(
                    Market.status == "active",
                    Market.blacklist_flag.is_(False),
                    Market.archived_flag.is_(False),
                )
            )
        )
        created = 0

        for market in markets:
            snapshot = await session.scalar(
                select(MarketSnapshot)
                .where(MarketSnapshot.market_id == market.id)
                .order_by(MarketSnapshot.captured_at.desc(), MarketSnapshot.id.desc())
            )
            if snapshot is None:
                continue

            analysis = await session.scalar(
                select(LLMAnalysis)
                .where(LLMAnalysis.market_id == market.id)
                .order_by(LLMAnalysis.created_at.desc(), LLMAnalysis.id.desc())
            )
            if analysis is None or not self._is_relevant(analysis.relevance):
                continue

            duplicate = await session.scalar(
                select(Signal.id).where(
                    Signal.market_id == market.id,
                    Signal.snapshot_id == snapshot.id,
                    Signal.strategy_config_id == strategy.id,
                )
            )
            if duplicate is not None:
                continue

            market_probability = self._clamp01(
                snapshot.implied_probability if snapshot.implied_probability is not None else snapshot.last_price
            )
            confidence = self._clamp01(analysis.confidence)
            model_probability = self._estimate_model_probability(
                market_probability=market_probability,
                impact_direction=analysis.impact_direction,
                impact_strength=analysis.impact_strength,
                confidence=confidence,
            )
            edge = model_probability - market_probability
            risk_flags = self._evaluate_risk_thresholds(
                strategy_parameters=strategy.parameters_json,
                confidence=confidence,
                edge=edge,
                liquidity=float(snapshot.liquidity or 0.0),
                market_probability=market_probability,
                spread=float(snapshot.spread or 0.0),
            )
            if risk_flags:
                status = "suppressed_by_risk"
            else:
                status = self._classify_signal(
                    edge=edge,
                    confidence=confidence,
                    parameters=strategy.parameters_json,
                )

            signal = Signal(
                market_id=market.id,
                snapshot_id=snapshot.id,
                market_probability=market_probability,
                model_probability=model_probability,
                edge=edge,
                confidence=confidence,
                status=status,
                explanation=analysis.summary or "Signal generated from latest analysis",
                risk_flags_json=risk_flags,
                strategy_config_id=strategy.id,
                strategy_version=f"{strategy.profile_name}:{strategy.version}",
                created_at=datetime.now(timezone.utc),
            )
            signal.analyses.append(analysis)
            if analysis.news_id:
                news_item = await session.scalar(select(News).where(News.id == analysis.news_id))
                if news_item is not None:
                    signal.news_items.append(news_item)
            session.add(signal)
            created += 1

        await session.commit()
        return created

    @staticmethod
    def _is_relevant(relevance: Any) -> bool:
        if relevance is None:
            return False
        value = str(relevance).strip().lower()
        return value in {"relevant", "high", "yes", "true", "1"}

    @staticmethod
    def _clamp01(value: Any) -> float:
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            numeric = 0.0
        if numeric < 0:
            return 0.0
        if numeric > 1:
            return 1.0
        return numeric

    def _estimate_model_probability(
        self,
        market_probability: float,
        impact_direction: str,
        impact_strength: float,
        confidence: float,
    ) -> float:
        sign = self._direction_sign(impact_direction)
        strength = self._clamp01(impact_strength)
        delta = strength * confidence * 0.5 * sign
        return self._clamp01(market_probability + delta)

    @staticmethod
    def _direction_sign(impact_direction: str) -> int:
        """Map LLM-reported direction into {-1, 0, +1}.

        Tolerates label drift the model produces in practice: "positive",
        "negative", compound forms like "neutral_to_slight_negative", and
        ambiguous labels like "mixed" → neutral.
        """
        token = str(impact_direction or "").strip().lower()
        if not token:
            return 0
        if "mixed" in token or "neutral" in token or "uncertain" in token:
            return 0
        positive_markers = ("yes", "positive", "increase", "bullish", "raise", "up")
        negative_markers = ("no", "negative", "decrease", "bearish", "lower", "down")
        for marker in negative_markers:
            if marker in token:
                return -1
        for marker in positive_markers:
            if marker in token:
                return 1
        return 0

    @classmethod
    def _classify_signal(
        cls,
        edge: float,
        confidence: float,
        parameters: dict[str, Any] | None = None,
    ) -> str:
        params = parameters or {}
        weak_conf = cls._param_float(
            params.get("weak_confidence_threshold"), default=0.45
        )
        info_edge = cls._param_float(
            params.get("informational_edge_threshold"), default=0.03
        )
        candidate_conf = cls._param_float(
            params.get("paper_trade_confidence_threshold"), default=0.75
        )
        candidate_edge = cls._param_float(
            params.get("paper_trade_edge_threshold"), default=0.08
        )

        abs_edge = abs(edge)
        if confidence < weak_conf:
            return "weak_signal"
        if abs_edge < info_edge:
            return "informational"
        if confidence >= candidate_conf and abs_edge >= candidate_edge:
            return "paper_trade_candidate"
        return "valid_signal"

    @staticmethod
    def _param_float(value: Any, *, default: float) -> float:
        if value is None:
            return default
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def _evaluate_risk_thresholds(
        self,
        strategy_parameters: dict[str, Any] | None,
        confidence: float,
        edge: float,
        liquidity: float,
        market_probability: float = 0.5,
        spread: float = 0.0,
    ) -> dict[str, bool]:
        params = strategy_parameters or {}
        flags: dict[str, bool] = {}

        min_confidence = self._to_float(params.get("min_confidence"))
        if min_confidence is not None and confidence < min_confidence:
            flags["min_confidence"] = True

        min_edge = self._to_float(params.get("min_edge"))
        if min_edge is not None and abs(edge) < min_edge:
            flags["min_edge"] = True

        min_liquidity = self._to_float(params.get("min_liquidity"))
        if min_liquidity is not None and liquidity < min_liquidity:
            flags["min_liquidity"] = True

        # Edge-of-distribution markets: TP/SL math gets weird, snapshot prices
        # are unreliable, and the "potential" PnL is mostly fake until the
        # market actually resolves. Suppress them by default.
        min_market_probability = self._to_float(params.get("min_market_probability"))
        if (
            min_market_probability is not None
            and market_probability < min_market_probability
        ):
            flags["min_market_probability"] = True

        max_market_probability = self._to_float(params.get("max_market_probability"))
        if (
            max_market_probability is not None
            and market_probability > max_market_probability
        ):
            flags["max_market_probability"] = True

        # Wide-spread markets: the "fair price" is undefined, and any close
        # would happen at a price we cannot actually trade at.
        max_allowed_spread = self._to_float(params.get("max_allowed_spread"))
        if max_allowed_spread is not None and spread > max_allowed_spread:
            flags["max_allowed_spread"] = True

        return flags

    @staticmethod
    def _to_float(value: Any) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
