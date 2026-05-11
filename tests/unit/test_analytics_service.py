from typing import Any

from app.schemas.api import StatsOut
from app.services.analytics_service import AnalyticsService


class FakeStrategy:
    def __init__(self, *, id: int = 2, version: int = 2) -> None:
        self.id = id
        self.version = version


class FakeAccount:
    def __init__(self, *, balance: float, initial_balance: float) -> None:
        self.balance = balance
        self.initial_balance = initial_balance


class FakeResult:
    def __init__(self, rows: list[tuple[Any, ...]]) -> None:
        self._rows = rows

    def all(self) -> list[tuple[Any, ...]]:
        return self._rows


class FakeSession:
    """Sequential-call fake. Order must match analytics_service.get_stats."""

    def __init__(self, scalar_values: list[Any], execute_results: list[FakeResult]) -> None:
        self._scalars = iter(scalar_values)
        self._execs = iter(execute_results)

    async def scalar(self, _stmt):
        return next(self._scalars)

    async def execute(self, _stmt):
        return next(self._execs)


async def test_get_stats_calculates_winrate_for_active_strategy() -> None:
    service = AnalyticsService()
    strategy = FakeStrategy(id=2, version=2)
    account = FakeAccount(balance=99.5, initial_balance=100.0)
    # Order:
    # 1) active strategy, 2) account,
    # 3) total_pt, 4) open, 5) closed, 6) winning,
    # 7) sum_pnl, 8) avg_pnl, 9) max_pnl, 10) min_pnl,
    # 11) locked_in_open, 12) active_signals_count, 13) total_signals
    session = FakeSession(
        scalar_values=[
            strategy,
            account,
            8,    # total_pt
            3,    # open
            4,    # closed
            1,    # winning
            2.5,  # sum_pnl
            0.625,
            1.5,
            -0.4,
            0.3,  # locked_in_open
            6,    # active_signals_count
            10,   # total_signals
        ],
        execute_results=[FakeResult([(1, 18, 0.09)])],
    )
    result = await service.get_stats(session=session)

    assert isinstance(result, StatsOut)
    assert result.active_strategy_version == 2
    assert result.total_signals == 10
    assert result.total_paper_trades == 8
    assert result.open_paper_trades == 3
    assert result.closed_paper_trades == 4
    assert result.winrate == 0.25
    assert result.total_pnl == 2.5
    assert result.avg_pnl == 0.625
    assert result.best_pnl == 1.5
    assert result.worst_pnl == -0.4
    assert result.balance == 99.5
    assert result.locked_in_open == 0.3
    assert result.equity == 99.8
    assert result.initial_balance == 100.0
    assert result.active_signals_count == 6
    assert len(result.past_strategies) == 1
    assert result.past_strategies[0].version == 1
    assert result.past_strategies[0].closed_trades == 18
    assert result.past_strategies[0].total_pnl == 0.09


async def test_get_stats_handles_zero_closed_trades() -> None:
    service = AnalyticsService()
    strategy = FakeStrategy(id=2, version=2)
    account = FakeAccount(balance=100.0, initial_balance=100.0)
    session = FakeSession(
        scalar_values=[strategy, account, 1, 1, 0, 0, 0.0, 0.0, 0.0, 0.0, 0.1, 0, 1],
        execute_results=[FakeResult([])],
    )
    result = await service.get_stats(session=session)
    assert result.winrate == 0.0
    assert result.total_pnl == 0.0
    assert result.balance == 100.0
    assert result.equity == 100.1
    assert result.past_strategies == []


async def test_get_stats_returns_empty_when_no_active_strategy() -> None:
    service = AnalyticsService()
    account = FakeAccount(balance=100.0, initial_balance=100.0)
    session = FakeSession(scalar_values=[None, account], execute_results=[])
    result = await service.get_stats(session=session)
    assert result.active_strategy_version is None
    assert result.balance == 100.0
    assert result.equity == 100.0
    assert result.closed_paper_trades == 0
