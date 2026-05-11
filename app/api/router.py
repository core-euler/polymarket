from fastapi import APIRouter

from app.api.routes.admin import router as admin_router
from app.api.routes.health import router as health_router
from app.api.routes.markets import router as markets_router
from app.api.routes.paper_trades import router as paper_trades_router
from app.api.routes.signals import router as signals_router
from app.api.routes.stats import router as stats_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health_router)
api_router.include_router(markets_router)
api_router.include_router(signals_router)
api_router.include_router(paper_trades_router)
api_router.include_router(stats_router)
api_router.include_router(admin_router)

