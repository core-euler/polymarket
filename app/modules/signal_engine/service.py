"""v5: the signal engine is RETIRED.

Trading decisions are made by the LLM trader (``app.modules.llm_trader``)
directly from LLMAnalysis + price + portfolio. The old edge formula
(``model_probability = clamp(market_probability + strength*confidence*0.5*sign)``;
``edge = model_probability - market_probability``) was proven fake by
construction — ``edge`` was just the LLM's own conviction ×0.5, never compared
to any outcome (see docs/STRATEGY_JOURNAL.md, v3/v4 verdicts).

This inert no-op is kept so existing imports and beat wiring stay valid; it
creates no signals. The ``signals`` table remains for historical audit.
"""

from __future__ import annotations

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

_log = structlog.get_logger("signal_engine")


class SignalEngineModule:
    async def generate_signals(self, session: AsyncSession) -> int:
        _ = session
        return 0
