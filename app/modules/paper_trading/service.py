"""v5: automatic open/close is RETIRED here — it moved to the LLM trader
(``app.modules.llm_trader``).

The v3/v4 logic that lived in this module (edge→direction entry, the v4 risk
layer of per-market caps / daily loss limit / correlation guard, and the
TP/SL/time/jump exits in ``monitor_open_trades``) was retired: ``edge`` was
fake by construction and the risk caps only masked a no-edge engine
(docs/STRATEGY_JOURNAL.md, v3/v4 verdicts). In v5 the trader LLM decides
open/close/hold/adjust, side, size and risk — there are no code-level trading
rules.

These inert no-ops are kept for import/beat compatibility.
"""

from __future__ import annotations

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

_log = structlog.get_logger("paper_trading")


class PaperTradingModule:
    async def open_eligible_trades(self, session: AsyncSession) -> int:
        _ = session
        return 0

    async def monitor_open_trades(self, session: AsyncSession) -> int:
        _ = session
        return 0
