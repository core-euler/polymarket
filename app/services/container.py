from dataclasses import dataclass

from app.core.config import Settings, get_settings
from app.services.analytics_service import AnalyticsService
from app.services.auth_service import AuthService
from app.services.market_service import MarketService
from app.services.paper_trade_service import PaperTradeService
from app.services.signal_service import SignalService


@dataclass(frozen=True)
class ServiceContainer:
    settings: Settings
    auth_service: AuthService
    market_service: MarketService
    signal_service: SignalService
    paper_trade_service: PaperTradeService
    analytics_service: AnalyticsService


def build_container() -> ServiceContainer:
    settings = get_settings()
    return ServiceContainer(
        settings=settings,
        auth_service=AuthService(settings),
        market_service=MarketService(),
        signal_service=SignalService(),
        paper_trade_service=PaperTradeService(),
        analytics_service=AnalyticsService(),
    )

