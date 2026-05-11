from datetime import datetime, timezone
from types import SimpleNamespace

from app.api.deps import get_container, get_session
from app.schemas.api import StatsOut


class DummyMarketService:
    async def list_markets(self, session, limit: int = 50):
        return [
            SimpleNamespace(
                id=1,
                polymarket_id="pm_1",
                title="Will X happen?",
                topic="politics",
                status="active",
                watchlist_flag=True,
                blacklist_flag=False,
                archived_flag=False,
            )
        ]


class DummySignalService:
    async def list_signals(self, session, limit: int = 50):
        return [
            SimpleNamespace(
                id=10,
                market_id=1,
                market_probability=0.51,
                model_probability=0.62,
                edge=0.11,
                confidence=0.7,
                status="valid_signal",
                explanation="Test signal",
                created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            )
        ]


class DummyPaperTradeService:
    async def list_trades(self, session, limit: int = 50):
        return [
            SimpleNamespace(
                id=100,
                signal_id=10,
                market_id=1,
                direction="YES",
                entry_price=0.62,
                position_size=100.0,
                status="open",
                open_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
            )
        ]


class DummyAnalyticsService:
    async def get_stats(self, session):
        return StatsOut(
            total_signals=1,
            total_paper_trades=1,
            open_paper_trades=1,
            closed_paper_trades=0,
            winrate=0.0,
        )


class DummyContainer:
    market_service = DummyMarketService()
    signal_service = DummySignalService()
    paper_trade_service = DummyPaperTradeService()
    analytics_service = DummyAnalyticsService()


async def _override_session():
    yield object()


def _override_container():
    return DummyContainer()


def test_markets_endpoint_with_overrides(api_app, client) -> None:
    api_app.dependency_overrides[get_session] = _override_session
    api_app.dependency_overrides[get_container] = _override_container

    response = client.get("/api/v1/markets")
    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["polymarket_id"] == "pm_1"

    api_app.dependency_overrides.clear()


def test_signals_endpoint_with_overrides(api_app, client) -> None:
    api_app.dependency_overrides[get_session] = _override_session
    api_app.dependency_overrides[get_container] = _override_container

    response = client.get("/api/v1/signals")
    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["status"] == "valid_signal"

    api_app.dependency_overrides.clear()


def test_paper_trades_endpoint_with_overrides(api_app, client) -> None:
    api_app.dependency_overrides[get_session] = _override_session
    api_app.dependency_overrides[get_container] = _override_container

    response = client.get("/api/v1/paper-trades")
    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["direction"] == "YES"

    api_app.dependency_overrides.clear()


def test_stats_endpoint_with_overrides(api_app, client) -> None:
    api_app.dependency_overrides[get_session] = _override_session
    api_app.dependency_overrides[get_container] = _override_container

    response = client.get("/api/v1/stats")
    assert response.status_code == 200
    payload = response.json()
    assert payload["total_signals"] == 1
    assert payload["winrate"] == 0.0

    api_app.dependency_overrides.clear()

