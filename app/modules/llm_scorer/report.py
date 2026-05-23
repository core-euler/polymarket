"""v5 calibration + edge report over llm_decisions.

Answers the only two questions that matter for LLM-as-trader:
  1. Calibration — when the trader says confidence 0.8, do ~80% of its
     directional calls actually move its way?
  2. Edge with decay-harvest ISOLATED — does it still predict moves once
     near-resolution markets (the longshot-decay zone that faked edge in
     v1-v4) are removed?

"Favorable" = the market's YES-probability moved in the call's direction by
+24h (YES -> price rose, NO -> price fell). This is a market-prediction
metric, independent of position sizing, so a few concentrated bets cannot
masquerade as skill the way headline PnL did.

Run on the server:
    docker compose run --rm api python -m app.modules.llm_scorer.report
"""

from collections import Counter

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.entities import LLMDecision

_CONF_BUCKETS = ((0.0, 0.5), (0.5, 0.7), (0.7, 0.85), (0.85, 1.01))


def _group_stats(items: list[dict]) -> dict:
    n = len(items)
    if n == 0:
        return {"n": 0, "favorable_rate": None, "avg_move_in_favor": None}
    favorable = sum(1 for it in items if it["favorable"])
    avg_move = sum(it["move_in_favor"] for it in items) / n
    return {"n": n, "favorable_rate": favorable / n, "avg_move_in_favor": avg_move}


async def build_report(
    session: AsyncSession, *, near_low: float = 0.15, near_high: float = 0.85
) -> dict:
    decisions = list(await session.scalars(select(LLMDecision)))
    by_action = Counter(d.action for d in decisions)
    graded = {
        "t1h": sum(1 for d in decisions if d.price_t1h is not None),
        "t4h": sum(1 for d in decisions if d.price_t4h is not None),
        "t24h": sum(1 for d in decisions if d.price_t24h is not None),
        "resolved": sum(1 for d in decisions if d.resolved_outcome),
    }

    directional: list[dict] = []
    for d in decisions:
        if d.action not in ("open", "adjust") or d.side not in ("YES", "NO"):
            continue
        if d.price_at_decision is None or d.price_t24h is None:
            continue
        p0 = float(d.price_at_decision)
        p1 = float(d.price_t24h)
        move = (p1 - p0) if d.side == "YES" else (p0 - p1)
        directional.append(
            {
                "confidence": float(d.confidence or 0.0),
                "p0": p0,
                "favorable": move > 0,
                "move_in_favor": move,
            }
        )

    calibration = []
    for lo, hi in _CONF_BUCKETS:
        items = [it for it in directional if lo <= it["confidence"] < hi]
        label = f"[{lo:.2f},{min(hi, 1.0):.2f})"
        calibration.append({"band": label, **_group_stats(items)})

    near = [it for it in directional if it["p0"] <= near_low or it["p0"] >= near_high]
    core = [it for it in directional if near_low < it["p0"] < near_high]
    edge = {
        "all": _group_stats(directional),
        "near_resolution": _group_stats(near),
        "core": _group_stats(core),
    }

    resolved_dir = [
        d for d in decisions if d.resolved_outcome in ("YES", "NO") and d.side in ("YES", "NO")
    ]
    if resolved_dir:
        correct = sum(1 for d in resolved_dir if d.side == d.resolved_outcome)
        resolution = {"n": len(resolved_dir), "accuracy": correct / len(resolved_dir)}
    else:
        resolution = {"n": 0, "accuracy": None}

    return {
        "total": len(decisions),
        "directional_n": len(directional),
        "by_action": dict(by_action),
        "graded": graded,
        "calibration": calibration,
        "edge": edge,
        "resolution": resolution,
    }


def _pct(value: float | None) -> str:
    return "  n/a" if value is None else f"{value * 100:5.1f}%"


def _signed(value: float | None) -> str:
    return "    n/a" if value is None else f"{value:+.4f}"


def format_report(report: dict) -> str:
    lines: list[str] = []
    lines.append("=== v5 LLM-trader scorecard ===")
    lines.append(
        f"decisions: {report['total']} total | "
        f"directional graded@24h: {report['directional_n']}"
    )
    actions = ", ".join(f"{k}={v}" for k, v in sorted(report["by_action"].items()))
    lines.append(f"by action: {actions or '(none)'}")
    g = report["graded"]
    lines.append(
        f"graded coverage: t1h={g['t1h']} t4h={g['t4h']} t24h={g['t24h']} "
        f"resolved={g['resolved']}"
    )

    lines.append("")
    lines.append("-- calibration (favorable move @ +24h, by stated confidence) --")
    lines.append("  band            n   favorable   avg move")
    for row in report["calibration"]:
        lines.append(
            f"  {row['band']:<12} {row['n']:>4}   {_pct(row['favorable_rate'])}   "
            f"{_signed(row['avg_move_in_favor'])}"
        )

    lines.append("")
    lines.append("-- edge isolation (decay-harvest separated) --")
    lines.append("  group              n   favorable   avg move")
    for key in ("all", "near_resolution", "core"):
        s = report["edge"][key]
        lines.append(
            f"  {key:<16} {s['n']:>4}   {_pct(s['favorable_rate'])}   "
            f"{_signed(s['avg_move_in_favor'])}"
        )
    lines.append("  (core = entry prob in (0.15,0.85); the real test of skill)")

    lines.append("")
    res = report["resolution"]
    lines.append(
        f"-- resolution accuracy: {res['n']} resolved directional calls, "
        f"side correct: {_pct(res['accuracy'])}"
    )
    return "\n".join(lines)


def main() -> None:
    import asyncio

    from app.db.session import SessionLocal

    async def _run() -> dict:
        async with SessionLocal() as session:
            return await build_report(session)

    print(format_report(asyncio.run(_run())))


if __name__ == "__main__":
    main()
