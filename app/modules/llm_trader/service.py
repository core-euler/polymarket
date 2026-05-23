"""v5 — LLM-as-trader.

ALL trading decisions (open/close/hold/adjust, side, size, risk) are made by
the trader LLM. This module is plumbing only:

1. trigger   — find "dirty" markets (new analysis OR significant price move OR
               a held position on a now-inactive market).
2. context   — build one batched brief over all dirty markets + the portfolio.
3. decide    — one LLM call returns a decisions JSON list.
4. execute   — apply decisions to paper_trades and log every decision to
               llm_decisions (the validation backbone).

There are deliberately NO code risk limits (no per-market cap, no daily loss
stop, no correlation guard, no TP/SL/time exits). The ONLY code-level invariant
is data integrity: we never fill a paper trade at a null/invalid price (that is
not a risk control, it is protection against writing garbage PnL — the v1 bug).
Position model: at most one open position per market; to change it the LLM uses
"adjust" or "close" (communicated to the model, not enforced as hidden policy).
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models import (
    LLMAnalysis,
    LLMDecision,
    Market,
    MarketSnapshot,
    PaperTrade,
    StrategyConfig,
)
from app.db.models.entities import VirtualAccount
from app.modules.llm_analysis.comet_client import CometAPIClient

_log = structlog.get_logger("llm_trader")


# ---------------------------------------------------------------------------
# Prompt + parsing (module-level so they are unit-testable in isolation)
# ---------------------------------------------------------------------------

def build_trader_prompt(context: dict[str, Any]) -> str:
    """Render the batched decision prompt from a context dict.

    The context carries the portfolio state and a per-market brief for every
    dirty market. We hand the model the raw structured data and ask for a
    strict-JSON decision list — the model forms its own probability view.
    """
    portfolio = json.dumps(context.get("portfolio", {}), ensure_ascii=False, indent=2)
    markets = json.dumps(context.get("markets", []), ensure_ascii=False, indent=2)
    return (
        "You are the sole trader for a Polymarket paper-trading account. You "
        "decide everything: whether to open, close, hold or adjust positions, "
        "which side (YES/NO), and the dollar size. There are NO automatic "
        "stop-losses, take-profits or risk caps — risk management is entirely "
        "your responsibility.\n\n"
        "Rules:\n"
        "- Each market has AT MOST ONE open position. To change an existing "
        "position use \"adjust\" (replaces it) or \"close\". \"open\" on a "
        "market that already has a position is ignored.\n"
        "- size is in dollars and cannot exceed the account balance "
        "(open_exposure is already locked).\n"
        "- A YES position profits if the YES probability rises; NO profits if "
        "it falls. current_price is the YES probability in [0,1].\n"
        "- Only act when you have a real informational reason. If nothing is "
        "actionable for a market, return action \"hold\".\n"
        "- Watch your own concentration and correlation across open positions "
        "(portfolio is shown). Nothing in code prevents over-concentration.\n\n"
        "Return STRICT JSON only (no prose, no markdown fences) with this shape:\n"
        "{\n"
        '  "decisions": [\n'
        '    {"market_id": <int>, "action": "open|close|hold|adjust", '
        '"side": "YES|NO", "size": <number>, "confidence": <0..1>, '
        '"rationale": "<short why>"}\n'
        "  ],\n"
        '  "portfolio_notes": "<overall exposure/concentration read>"\n'
        "}\n"
        "Include one decision object per market_id listed below.\n\n"
        f"PORTFOLIO:\n{portfolio}\n\n"
        f"MARKETS (each is 'dirty' — new info or a price move):\n{markets}\n"
    )


def parse_decisions(raw: dict[str, Any]) -> dict[str, Any]:
    """Extract {"decisions": [...], "portfolio_notes": str} from a raw Comet
    chat-completions response. Tolerant to fenced/embedded JSON; returns empty
    decisions on any parse failure (fail closed → no trades)."""
    default: dict[str, Any] = {"decisions": [], "portfolio_notes": ""}
    content = _extract_content_text(raw)
    payload = _parse_json_payload(content)
    if not isinstance(payload, dict):
        return default
    decisions = payload.get("decisions")
    if not isinstance(decisions, list):
        decisions = []
    return {
        "decisions": [d for d in decisions if isinstance(d, dict)],
        "portfolio_notes": str(payload.get("portfolio_notes", "")),
    }


def _extract_content_text(raw: dict[str, Any]) -> str:
    choices = raw.get("choices") if isinstance(raw, dict) else None
    if not isinstance(choices, list) or not choices:
        return ""
    first = choices[0]
    if not isinstance(first, dict):
        return ""
    message = first.get("message")
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        chunks = [p.get("text", "") for p in content if isinstance(p, dict)]
        return "\n".join(c for c in chunks if isinstance(c, str))
    return ""


def _parse_json_payload(content: str) -> dict[str, Any] | None:
    text = (content or "").strip()
    if not text:
        return None
    for candidate in (
        text,
        re.sub(r"\s*```$", "", re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)).strip(),
    ):
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        try:
            parsed = json.loads(text[start : end + 1])
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            return None
    return None


# ---------------------------------------------------------------------------
# Trader clients
# ---------------------------------------------------------------------------

class NullTrader:
    model_name = "null-trader"

    async def decide(self, context: dict[str, Any]) -> dict[str, Any]:
        _ = context
        return {"decisions": [], "portfolio_notes": "null-trader: no API key"}


class CometTrader:
    """Wraps the Comet client with the trader model and JSON parsing."""

    def __init__(self, client: Any | None = None, model: str | None = None) -> None:
        settings = get_settings()
        resolved = model or settings.comet_model_trader or settings.comet_model_default
        # Trader calls carry a fat batched context — allow a longer timeout.
        self.client = client or CometAPIClient(model=resolved, timeout=120.0)
        self.model_name = resolved or "comet-trader"

    async def decide(self, context: dict[str, Any]) -> dict[str, Any]:
        prompt = build_trader_prompt(context)
        raw = await self.client.analyze_text(prompt)
        return parse_decisions(raw)


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

class LLMTraderModule:
    def __init__(
        self,
        *,
        trader: Any | None = None,
        price_move_threshold: float = 0.03,
        history_limit: int = 8,
        analysis_limit: int = 5,
        analysis_lookback_hours: float = 24.0,
    ) -> None:
        self._trader = trader
        self.price_move_threshold = max(0.0, float(price_move_threshold))
        self.history_limit = max(1, int(history_limit))
        self.analysis_limit = max(1, int(analysis_limit))
        self.analysis_lookback = timedelta(hours=max(0.0, float(analysis_lookback_hours)))

    def _get_trader(self) -> Any:
        if self._trader is None:
            self._trader = CometTrader() if get_settings().comet_api_key else NullTrader()
        return self._trader

    async def _get_account(self, session: AsyncSession) -> VirtualAccount | None:
        return await session.scalar(select(VirtualAccount).order_by(VirtualAccount.id.asc()))

    async def _get_active_strategy(self, session: AsyncSession) -> StrategyConfig | None:
        return await session.scalar(
            select(StrategyConfig)
            .where(StrategyConfig.active_flag.is_(True))
            .order_by(StrategyConfig.version.desc(), StrategyConfig.id.desc())
        )

    async def run_cycle(self, session: AsyncSession) -> int:
        account = await self._get_account(session)
        strategy = await self._get_active_strategy(session)
        if account is None or strategy is None:
            return 0

        dirty = await self._dirty_markets(session)
        if not dirty:
            _log.info("llm_trader.no_dirty_markets")
            return 0

        context = await self._build_context(session, account, dirty)
        trader = self._get_trader()
        try:
            result = await trader.decide(context)
        except Exception as exc:  # noqa: BLE001 — never let a bad LLM call crash the beat
            _log.warning("llm_trader.decide_failed", error=str(exc), markets=len(dirty))
            return 0

        executed = await self._execute(session, account, strategy, dirty, result)
        await session.commit()
        _log.info(
            "llm_trader.cycle_done",
            dirty=len(dirty),
            decisions=len(result.get("decisions", [])),
            executed=executed,
        )
        return executed

    # --- trigger -----------------------------------------------------------

    async def _dirty_markets(self, session: AsyncSession) -> list[dict[str, Any]]:
        now = datetime.now(timezone.utc)
        markets = list(
            await session.scalars(
                select(Market).where(
                    Market.status == "active",
                    Market.blacklist_flag.is_(False),
                    Market.archived_flag.is_(False),
                )
            )
        )
        seen = {m.id for m in markets}
        # Markets with an open position but no longer active → surface for the
        # LLM to settle (event = market_inactive); the LLM still makes the call.
        open_market_ids = set(
            await session.scalars(select(PaperTrade.market_id).where(PaperTrade.status == "open"))
        )
        missing = open_market_ids - seen
        if missing:
            markets += list(await session.scalars(select(Market).where(Market.id.in_(missing))))

        dirty: list[dict[str, Any]] = []
        for market in markets:
            snapshot = await session.scalar(
                select(MarketSnapshot)
                .where(MarketSnapshot.market_id == market.id)
                .order_by(MarketSnapshot.captured_at.desc(), MarketSnapshot.id.desc())
            )
            if snapshot is None:
                continue  # cannot price it → cannot trade it

            open_trade = await session.scalar(
                select(PaperTrade).where(
                    PaperTrade.market_id == market.id, PaperTrade.status == "open"
                )
            )
            last_decision = await session.scalar(
                select(LLMDecision)
                .where(LLMDecision.market_id == market.id)
                .order_by(LLMDecision.decided_at.desc(), LLMDecision.id.desc())
            )
            latest_analysis = await session.scalar(
                select(LLMAnalysis)
                .where(LLMAnalysis.market_id == market.id)
                .order_by(LLMAnalysis.created_at.desc(), LLMAnalysis.id.desc())
            )

            reason = self._classify_dirty(
                now=now,
                market=market,
                snapshot=snapshot,
                open_trade=open_trade,
                last_decision=last_decision,
                latest_analysis=latest_analysis,
            )
            if reason is None:
                continue
            dirty.append(
                {"market": market, "snapshot": snapshot, "open_trade": open_trade, "reason": reason}
            )
        return dirty

    def _classify_dirty(
        self,
        *,
        now: datetime,
        market: Market,
        snapshot: MarketSnapshot,
        open_trade: PaperTrade | None,
        last_decision: LLMDecision | None,
        latest_analysis: LLMAnalysis | None,
    ) -> str | None:
        # A held position on an inactive/resolved market: surface for settlement.
        if market.status != "active" and open_trade is not None:
            return "market_inactive"

        # New analysis since the last decision (or first-ever, if recent).
        if latest_analysis is not None and str(latest_analysis.relevance).lower() in (
            "relevant",
            "high",
            "yes",
            "true",
            "1",
        ):
            created = _aware(latest_analysis.created_at)
            if last_decision is None:
                if created is not None and (now - created) <= self.analysis_lookback:
                    return "new_analysis"
            elif created is not None and created > _aware(last_decision.decided_at):
                return "new_analysis"

        # Significant price move vs the reference price (last decision, else the
        # open position's entry). No reference and no position → not dirty.
        price = _snapshot_price(snapshot)
        ref = None
        if last_decision is not None and last_decision.price_at_decision:
            ref = float(last_decision.price_at_decision)
        elif open_trade is not None:
            ref = float(open_trade.entry_price)
        if ref is not None and price > 0 and abs(price - ref) >= self.price_move_threshold:
            return "price_move"
        return None

    # --- context -----------------------------------------------------------

    async def _build_context(
        self, session: AsyncSession, account: VirtualAccount, dirty: list[dict[str, Any]]
    ) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        open_trades = list(
            await session.scalars(select(PaperTrade).where(PaperTrade.status == "open"))
        )
        portfolio = {
            "balance": round(float(account.balance), 4),
            "open_exposure": round(sum(float(t.position_size) for t in open_trades), 4),
            "open_positions": [
                {
                    "market_id": t.market_id,
                    "side": t.direction,
                    "size": round(float(t.position_size), 4),
                    "entry_price": round(float(t.entry_price), 4),
                }
                for t in open_trades
            ],
        }

        markets_ctx: list[dict[str, Any]] = []
        for d in dirty:
            market: Market = d["market"]
            snapshot: MarketSnapshot = d["snapshot"]
            pos: PaperTrade | None = d["open_trade"]
            markets_ctx.append(
                {
                    "market_id": market.id,
                    "question": market.question,
                    "market_status": market.status,
                    "trigger": d["reason"],
                    "current_price": round(_snapshot_price(snapshot), 4),
                    "price_history": await self._price_history(session, market.id),
                    "news": await self._recent_analyses(session, market.id),
                    "position": (
                        {
                            "side": pos.direction,
                            "size": round(float(pos.position_size), 4),
                            "entry_price": round(float(pos.entry_price), 4),
                            "age_minutes": _age_minutes(now, pos.open_time),
                        }
                        if pos is not None
                        else None
                    ),
                }
            )
        return {"portfolio": portfolio, "markets": markets_ctx}

    async def _price_history(self, session: AsyncSession, market_id: int) -> list[dict[str, Any]]:
        rows = list(
            await session.scalars(
                select(MarketSnapshot)
                .where(MarketSnapshot.market_id == market_id)
                .order_by(MarketSnapshot.captured_at.desc(), MarketSnapshot.id.desc())
                .limit(self.history_limit)
            )
        )
        rows.reverse()  # chronological for the model
        return [
            {"t": _iso(s.captured_at), "p": round(_snapshot_price(s), 4)} for s in rows
        ]

    async def _recent_analyses(self, session: AsyncSession, market_id: int) -> list[dict[str, Any]]:
        rows = list(
            await session.scalars(
                select(LLMAnalysis)
                .where(LLMAnalysis.market_id == market_id)
                .order_by(LLMAnalysis.created_at.desc(), LLMAnalysis.id.desc())
                .limit(self.analysis_limit)
            )
        )
        return [
            {
                "summary": (a.summary or "")[:600],
                "relevance": a.relevance,
                "at": _iso(a.created_at),
            }
            for a in rows
        ]

    # --- execution ---------------------------------------------------------

    async def _execute(
        self,
        session: AsyncSession,
        account: VirtualAccount,
        strategy: StrategyConfig,
        dirty: list[dict[str, Any]],
        result: dict[str, Any],
    ) -> int:
        now = datetime.now(timezone.utc)
        by_id = {d["market"].id: d for d in dirty}
        model_name = getattr(self._get_trader(), "model_name", "")
        executed = 0

        for dec in result.get("decisions", []):
            mid = _to_int(dec.get("market_id"))
            ctx = by_id.get(mid)
            if ctx is None:
                continue  # hallucinated or non-dirty market — ignore silently

            action = str(dec.get("action", "hold")).strip().lower()
            raw_side = dec.get("side")
            side = str(raw_side).strip().upper() if raw_side else None
            size = _to_float(dec.get("size"))
            confidence = _to_float(dec.get("confidence"))
            rationale = str(dec.get("rationale", ""))[:2000]
            price = _snapshot_price(ctx["snapshot"])
            open_trade: PaperTrade | None = ctx["open_trade"]

            log = LLMDecision(
                market_id=mid,
                strategy_config_id=strategy.id,
                decided_at=now,
                action=action,
                side=side if side in ("YES", "NO") else None,
                size=size,
                confidence=confidence,
                rationale=rationale,
                price_at_decision=(price if price > 0 else None),
                model_name=model_name,
                trigger_reason=str(ctx["reason"]),
                executed=False,
                trace_json={},
            )

            # Data-integrity carve-out: never act on a null/invalid price.
            if action in ("open", "close", "adjust") and price <= 0:
                log.execution_note = "skipped: null/invalid price"
                session.add(log)
                continue

            if action == "hold":
                log.execution_note = "hold"
                session.add(log)
                continue

            if action == "close":
                if open_trade is None:
                    log.execution_note = "no open position to close"
                    session.add(log)
                    continue
                self._close_trade(account, open_trade, price, now, "llm_close")
                session.add(log)
                await session.flush()
                log.executed = True
                log.paper_trade_id = open_trade.id
                executed += 1
                continue

            if action in ("open", "adjust"):
                if action == "adjust" and open_trade is not None:
                    # Replace the existing position: realize it, then reopen.
                    self._close_trade(account, open_trade, price, now, "llm_adjust")
                    open_trade = None
                if open_trade is not None:
                    log.execution_note = "already open (use adjust/close)"
                    session.add(log)
                    continue
                if side not in ("YES", "NO"):
                    log.execution_note = "invalid side"
                    session.add(log)
                    continue
                if size <= 0:
                    log.execution_note = "invalid size"
                    session.add(log)
                    continue
                if size > float(account.balance):
                    log.execution_note = "insufficient balance"
                    session.add(log)
                    continue
                trade = PaperTrade(
                    signal_id=None,
                    market_id=mid,
                    direction=side,
                    entry_price=price,
                    position_size=size,
                    open_time=now,
                    status="open",
                    open_reason=("llm_trader: " + rationale)[:500],
                    strategy_config_id=strategy.id,
                    strategy_version=f"{strategy.profile_name}:{strategy.version}",
                )
                session.add(trade)
                account.balance = float(account.balance) - size
                session.add(log)
                await session.flush()
                log.executed = True
                log.paper_trade_id = trade.id
                executed += 1
                continue

            log.execution_note = f"unknown action: {action}"
            session.add(log)

        return executed

    @staticmethod
    def _close_trade(
        account: VirtualAccount | None,
        trade: PaperTrade,
        price: float,
        now: datetime,
        reason: str,
    ) -> None:
        if trade.direction == "YES":
            delta = price - float(trade.entry_price)
        else:
            delta = float(trade.entry_price) - price
        pnl = delta * float(trade.position_size)
        trade.status = "closed"
        trade.exit_price = price
        trade.close_time = now
        trade.realized_pnl = pnl
        trade.close_reason = reason
        if account is not None:
            account.balance = float(account.balance) + float(trade.position_size) + pnl


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------

def _snapshot_price(snapshot: MarketSnapshot | None) -> float:
    if snapshot is None:
        return 0.0
    return float(snapshot.implied_probability or snapshot.last_price or 0.0)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _iso(value: datetime | None) -> str:
    aware = _aware(value)
    return aware.isoformat() if aware is not None else ""


def _age_minutes(now: datetime, open_time: datetime) -> int:
    ot = _aware(open_time)
    if ot is None:
        return 0
    return int((now - ot).total_seconds() // 60)


def _to_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _to_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
