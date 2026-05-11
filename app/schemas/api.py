from datetime import datetime

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = "ok"


class MarketOut(BaseModel):
    id: int
    polymarket_id: str
    title: str
    topic: str
    status: str
    watchlist_flag: bool
    blacklist_flag: bool
    archived_flag: bool


class SignalOut(BaseModel):
    id: int
    market_id: int
    market_probability: float
    model_probability: float
    edge: float
    confidence: float
    status: str
    explanation: str
    created_at: datetime


class PaperTradeOut(BaseModel):
    id: int
    signal_id: int
    market_id: int
    direction: str
    entry_price: float
    position_size: float
    status: str
    open_time: datetime


class RunPipelineResponse(BaseModel):
    queued: bool = True
    chain_id: str | None = None
    steps: list[str] = Field(default_factory=list)


class PastStrategySummary(BaseModel):
    version: int
    closed_trades: int
    total_pnl: float


class StatsOut(BaseModel):
    active_strategy_version: int | None = None
    total_signals: int = 0
    total_paper_trades: int = 0
    open_paper_trades: int = 0
    closed_paper_trades: int = 0
    winrate: float = Field(default=0, ge=0, le=1)
    balance: float = 0.0
    locked_in_open: float = 0.0
    equity: float = 0.0
    initial_balance: float = 0.0
    total_pnl: float = 0.0
    avg_pnl: float = 0.0
    best_pnl: float = 0.0
    worst_pnl: float = 0.0
    active_signals_count: int = 0
    past_strategies: list[PastStrategySummary] = Field(default_factory=list)

