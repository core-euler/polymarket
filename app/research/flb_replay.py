"""Survivorship-free favorite-longshot-bias (FLB) replay — offline pre-mortem for v6.

Tests ONE hypothesis before any v6 trading code is written: does fading retail
longshots (taking the NO side of a market priced low on YES) have positive
REALIZED edge on Polymarket, after spread, measured to ACTUAL resolution?

Why offline + to-resolution: every prior version (v1-v5) measured something
other than the realized outcome (clamp marks, +24h price drift) and mistook
artifacts for edge. This pulls EVERY resolved market matching an ex-ante
trigger — winners and losers, no look-ahead — and scores each at resolution.

The estimator: selling one YES contract at price p (= taking the NO side) pays
+p if the market resolves NO and -(1-p) if it resolves YES. Mean PnL per
contract across triggered markets = p_bar - q_empirical (gross), minus spread.
That is positive only if longshots are systematically overpriced (real FLB) —
time decay alone is a martingale and nets to zero on a fairly priced book.

This run is deliberately RAW: algorithmic trigger only, no LLM news filter, so
we measure the base-rate inefficiency before layering anything that could
smuggle back the (already refuted) "the model can forecast" claim.

Run (no DB; hits the public Polymarket API):
    python -m app.research.flb_replay
"""

import asyncio
import json
from datetime import datetime, timezone
from typing import Any

from app.modules.market_data.polymarket_client import PolymarketClient


# --- pure scoring (unit-tested, no network) --------------------------------

def _as_list(value: Any) -> list:
    """Gamma encodes outcomes/clobTokenIds/outcomePrices as JSON strings."""
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
        return parsed if isinstance(parsed, list) else []
    return []


def is_binary_yes_no(market: dict) -> bool:
    outcomes = [str(o).strip().lower() for o in _as_list(market.get("outcomes"))]
    return outcomes == ["yes", "no"]


def parse_outcome(market: dict, *, eps: float = 0.05) -> str | None:
    """Resolution from outcomePrices ([yes, no]): YES if yes~1, NO if yes~0."""
    prices = _as_list(market.get("outcomePrices"))
    if len(prices) != 2:
        return None
    try:
        yes = float(prices[0])
    except (TypeError, ValueError):
        return None
    if yes >= 1.0 - eps:
        return "YES"
    if yes <= eps:
        return "NO"
    return None  # ambiguous / not cleanly resolved -> excluded


def yes_token_id(market: dict) -> str | None:
    tokens = _as_list(market.get("clobTokenIds"))
    if tokens and tokens[0]:
        return str(tokens[0])
    return None


def iso_to_ts(value: str | None) -> int | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


def find_entry(
    history: list[dict],
    end_ts: int,
    *,
    low: float,
    high: float,
    min_days: float,
    max_days: float,
) -> dict | None:
    """Earliest point with price in [low,high] and runway in (min_days,max_days].

    Ex-ante: only price + calendar known at that timestamp are used; the
    resolution outcome is never consulted here, so there is no look-ahead.
    """
    pts = sorted(
        (
            {"t": int(h["t"]), "p": float(h["p"])}
            for h in history
            if h.get("t") is not None and h.get("p") is not None
        ),
        key=lambda h: h["t"],
    )
    for h in pts:
        days = (end_ts - h["t"]) / 86400.0
        if not (min_days < days <= max_days):
            continue
        if low <= h["p"] <= high:
            return {"entry_ts": h["t"], "entry_price": h["p"], "days_to_res": days}
    return None


def position_pnl(entry_price: float, outcome: str, *, spread: float = 0.0) -> float:
    """Realized PnL per contract of the NO (fade-the-longshot) position.

    You sell YES at the bid (mid minus half the spread); NO wins -> keep it,
    YES wins -> pay out 1.
    """
    eff = entry_price - spread / 2.0
    return eff if outcome == "NO" else eff - 1.0


def summarize(rows: list[dict], *, spread: float = 0.0) -> dict:
    n = len(rows)
    if n == 0:
        return {"n": 0}
    entries = [r["entry_price"] for r in rows]
    yes_n = sum(1 for r in rows if r["outcome"] == "YES")
    p_bar = sum(entries) / n
    q_emp = yes_n / n
    pnls = [position_pnl(r["entry_price"], r["outcome"], spread=spread) for r in rows]
    cum = peak = max_dd = 0.0
    for r in sorted(rows, key=lambda r: r["end_ts"]):
        cum += position_pnl(r["entry_price"], r["outcome"], spread=spread)
        peak = max(peak, cum)
        max_dd = min(max_dd, cum - peak)
    return {
        "n": n,
        "mean_entry": p_bar,          # p_bar
        "yes_rate": q_emp,            # q_empirical: how often the longshot HIT
        "no_win_rate": 1.0 - q_emp,
        "gross_edge": p_bar - q_emp,  # EV/contract before spread
        "mean_pnl": sum(pnls) / n,    # EV/contract at the given spread
        "worst": min(pnls),
        "best": max(pnls),
        "max_drawdown": max_dd,       # cumulative path, ordered by resolution date
    }


# --- offline runner --------------------------------------------------------

async def run_replay(
    *,
    low: float = 0.05,
    high: float = 0.15,
    min_days: float = 7.0,
    max_days: float = 90.0,
    min_volume: float = 10_000.0,
    max_markets: int = 400,
    concurrency: int = 6,
    fidelity: int = 60,
    spreads: tuple[float, ...] = (0.0, 0.02, 0.04),
    client: PolymarketClient | None = None,
) -> dict:
    client = client or PolymarketClient()
    markets = await client.list_resolved_markets()

    candidates: list[dict] = []
    for m in markets:
        if not is_binary_yes_no(m):
            continue
        outcome = parse_outcome(m)
        token = yes_token_id(m)
        end_ts = iso_to_ts(m.get("endDate") or m.get("endDateIso"))
        if outcome is None or token is None or end_ts is None:
            continue
        try:
            vol = float(m.get("volumeNum") or m.get("volume") or 0)
        except (TypeError, ValueError):
            vol = 0.0
        if vol < min_volume:
            continue
        candidates.append(
            {"market": m, "outcome": outcome, "token": token, "end_ts": end_ts}
        )
        if len(candidates) >= max_markets:
            break

    sem = asyncio.Semaphore(concurrency)
    rows: list[dict] = []

    async def _eval(c: dict) -> None:
        start = c["end_ts"] - int(max_days * 86400) - 86400
        async with sem:
            try:
                hist = await client.get_prices_history(
                    c["token"], start_ts=start, end_ts=c["end_ts"], fidelity=fidelity
                )
            except Exception:
                return
        entry = find_entry(
            hist, c["end_ts"], low=low, high=high, min_days=min_days, max_days=max_days
        )
        if entry is None:
            return
        rows.append(
            {
                **entry,
                "outcome": c["outcome"],
                "end_ts": c["end_ts"],
                "question": str(c["market"].get("question", ""))[:70],
            }
        )

    await asyncio.gather(*(_eval(c) for c in candidates))

    return {
        "scanned": len(markets),
        "candidates": len(candidates),
        "triggered": len(rows),
        "by_spread": {f"{s:.2f}": summarize(rows, spread=s) for s in spreads},
        "rows": rows,
    }


def format_replay(result: dict) -> str:
    lines = ["=== FLB replay (survivorship-free, scored to resolution) ==="]
    lines.append(f"scanned resolved markets:  {result['scanned']}")
    lines.append(f"binary/liquid candidates:  {result['candidates']}")
    lines.append(f"triggered (entry found):   {result['triggered']}")
    base = result["by_spread"].get("0.00", {})
    if not base.get("n"):
        lines.append("  (no markets triggered — widen the window or lower min_volume)")
        return "\n".join(lines)

    lines.append("")
    lines.append(f"mean entry price (p_bar):  {base['mean_entry']:.4f}")
    lines.append(
        f"longshot HIT rate (q):     {base['yes_rate']:.4f}   "
        f"(q < p_bar => FLB present)"
    )
    lines.append(f"gross edge per contract:   {base['gross_edge']:+.4f}   (= p_bar - q)")
    lines.append("")
    lines.append("  spread   mean PnL/contract   max drawdown   worst    best")
    for key in ("0.00", "0.02", "0.04"):
        s = result["by_spread"].get(key)
        if not s or not s.get("n"):
            continue
        lines.append(
            f"  {key}     {s['mean_pnl']:+.4f}              {s['max_drawdown']:+.3f}   "
            f"{s['worst']:+.3f}   {s['best']:+.3f}"
        )
    lines.append("")
    lines.append("  read: mean PnL > 0 after a realistic spread (>= 0.02) AND a")
    lines.append("        survivable drawdown => real FLB edge, worth a v6.")
    lines.append("        otherwise => publish the negative result, now isolated.")
    return "\n".join(lines)


def main() -> None:
    result = asyncio.run(run_replay())
    print(format_replay(result))


if __name__ == "__main__":
    main()
