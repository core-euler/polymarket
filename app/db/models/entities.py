from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.common import TimestampMixin


signal_news = Table(
    "signal_news",
    Base.metadata,
    Column("signal_id", ForeignKey("signals.id", ondelete="CASCADE"), primary_key=True),
    Column("news_id", ForeignKey("news.id", ondelete="CASCADE"), primary_key=True),
)

signal_analyses = Table(
    "signal_analyses",
    Base.metadata,
    Column("signal_id", ForeignKey("signals.id", ondelete="CASCADE"), primary_key=True),
    Column("llm_analysis_id", ForeignKey("llm_analyses.id", ondelete="CASCADE"), primary_key=True),
)


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    username: Mapped[str] = mapped_column(String(255), default="")
    role: Mapped[str] = mapped_column(String(64), default="owner")
    access_status: Mapped[str] = mapped_column(String(32), default="active")
    notification_settings: Mapped[dict] = mapped_column(JSON, default=dict)


class Market(TimestampMixin, Base):
    __tablename__ = "markets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    polymarket_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    slug: Mapped[str] = mapped_column(String(255), default="", index=True)
    title: Mapped[str] = mapped_column(String(512))
    question: Mapped[str] = mapped_column(Text)
    topic: Mapped[str] = mapped_column(String(128), default="")
    status: Mapped[str] = mapped_column(String(64), default="active")
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    watchlist_flag: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    blacklist_flag: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    archived_flag: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    yes_token_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    no_token_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    snapshots: Mapped[list["MarketSnapshot"]] = relationship(back_populates="market")


class MarketSnapshot(Base):
    __tablename__ = "market_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    market_id: Mapped[int] = mapped_column(ForeignKey("markets.id", ondelete="CASCADE"), index=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    last_price: Mapped[float] = mapped_column(Float, default=0)
    implied_probability: Mapped[float] = mapped_column(Float, default=0)
    liquidity: Mapped[float] = mapped_column(Float, default=0)
    spread: Mapped[float] = mapped_column(Float, default=0)
    volume: Mapped[float] = mapped_column(Float, default=0)
    raw_payload: Mapped[dict] = mapped_column(JSON, default=dict)

    market: Mapped["Market"] = relationship(back_populates="snapshots")


class Source(TimestampMixin, Base):
    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255))
    source_type: Mapped[str] = mapped_column(String(64))
    url: Mapped[str] = mapped_column(String(1024))
    domain: Mapped[str] = mapped_column(String(255), default="")
    topic: Mapped[str] = mapped_column(String(128), default="")
    language: Mapped[str] = mapped_column(String(16), default="en")
    trust_score: Mapped[float] = mapped_column(Float, default=0.5)
    priority: Mapped[int] = mapped_column(Integer, default=0)
    active_flag: Mapped[bool] = mapped_column(Boolean, default=True)


class News(Base):
    __tablename__ = "news"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"), index=True)
    title: Mapped[str] = mapped_column(String(1024))
    url: Mapped[str] = mapped_column(String(2048), unique=True)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    summary_text: Mapped[str] = mapped_column(Text, default="")
    raw_content: Mapped[str] = mapped_column(Text, default="")
    language: Mapped[str] = mapped_column(String(16), default="en")
    content_hash: Mapped[str] = mapped_column(String(128), index=True)
    topic: Mapped[str] = mapped_column(String(128), default="")
    processing_status: Mapped[str] = mapped_column(String(64), default="new", index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        index=True,
    )


class LLMAnalysis(Base):
    __tablename__ = "llm_analyses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    news_id: Mapped[int] = mapped_column(ForeignKey("news.id"), index=True)
    market_id: Mapped[int] = mapped_column(ForeignKey("markets.id"), index=True)
    model_name: Mapped[str] = mapped_column(String(128))
    prompt_template_version: Mapped[str] = mapped_column(String(64), default="v1")
    relevance: Mapped[str] = mapped_column(String(32), default="unknown")
    event_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    impact_direction: Mapped[str] = mapped_column(String(32), default="neutral")
    impact_strength: Mapped[float] = mapped_column(Float, default=0)
    confidence: Mapped[float] = mapped_column(Float, default=0)
    facts_json: Mapped[dict] = mapped_column(JSON, default=dict)
    entities_json: Mapped[dict] = mapped_column(JSON, default=dict)
    uncertainties_json: Mapped[dict] = mapped_column(JSON, default=dict)
    contradictions_json: Mapped[dict] = mapped_column(JSON, default=dict)
    summary: Mapped[str] = mapped_column(Text, default="")
    trace_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class StrategyConfig(Base):
    __tablename__ = "strategy_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    profile_name: Mapped[str] = mapped_column(String(128), index=True)
    version: Mapped[int] = mapped_column(Integer, index=True)
    parameters_json: Mapped[dict] = mapped_column(JSON, default=dict)
    paper_trading_rules_json: Mapped[dict] = mapped_column(JSON, default=dict)
    antipattern_rules_json: Mapped[dict] = mapped_column(JSON, default=dict)
    active_flag: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

    __table_args__ = (UniqueConstraint("profile_name", "version", name="uq_strategy_profile_version"),)


class Signal(Base):
    __tablename__ = "signals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    market_id: Mapped[int] = mapped_column(ForeignKey("markets.id"), index=True)
    snapshot_id: Mapped[int] = mapped_column(ForeignKey("market_snapshots.id"), index=True)
    market_probability: Mapped[float] = mapped_column(Float, default=0)
    model_probability: Mapped[float] = mapped_column(Float, default=0)
    edge: Mapped[float] = mapped_column(Float, default=0)
    confidence: Mapped[float] = mapped_column(Float, default=0)
    status: Mapped[str] = mapped_column(String(64), index=True)
    explanation: Mapped[str] = mapped_column(Text, default="")
    risk_flags_json: Mapped[dict] = mapped_column(JSON, default=dict)
    strategy_config_id: Mapped[int] = mapped_column(ForeignKey("strategy_configs.id"), index=True)
    strategy_version: Mapped[str] = mapped_column(String(64), default="v1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

    news_items: Mapped[list["News"]] = relationship(secondary=signal_news)
    analyses: Mapped[list["LLMAnalysis"]] = relationship(secondary=signal_analyses)


class PaperTrade(Base):
    __tablename__ = "paper_trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    signal_id: Mapped[int] = mapped_column(ForeignKey("signals.id"), index=True)
    market_id: Mapped[int] = mapped_column(ForeignKey("markets.id"), index=True)
    direction: Mapped[str] = mapped_column(String(16))
    entry_price: Mapped[float] = mapped_column(Float)
    position_size: Mapped[float] = mapped_column(Float)
    open_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    open_reason: Mapped[str] = mapped_column(Text)
    strategy_config_id: Mapped[int] = mapped_column(ForeignKey("strategy_configs.id"), index=True)
    strategy_version: Mapped[str] = mapped_column(String(64), default="v1")
    exit_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    close_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    close_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    realized_pnl: Mapped[Optional[float]] = mapped_column(Float, nullable=True)


class ErrorReview(Base):
    __tablename__ = "error_reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    review_target_type: Mapped[str] = mapped_column(String(32), index=True)
    review_target_id: Mapped[int] = mapped_column(Integer, index=True)
    error_type: Mapped[str] = mapped_column(String(128), index=True)
    severity: Mapped[str] = mapped_column(String(32), index=True)
    origin: Mapped[str] = mapped_column(String(32), index=True)
    comment: Mapped[str] = mapped_column(Text, default="")
    created_by_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class Antipattern(TimestampMixin, Base):
    __tablename__ = "antipatterns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text)
    detection_logic_description: Mapped[str] = mapped_column(Text, default="")
    penalty_action: Mapped[str] = mapped_column(String(64))
    penalty_value: Mapped[float] = mapped_column(Float, default=0)
    active_flag: Mapped[bool] = mapped_column(Boolean, default=True, index=True)


class SignalAntipattern(Base):
    __tablename__ = "signal_antipatterns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    signal_id: Mapped[int] = mapped_column(ForeignKey("signals.id"), index=True)
    antipattern_id: Mapped[int] = mapped_column(ForeignKey("antipatterns.id"), index=True)
    assignment_mode: Mapped[str] = mapped_column(String(16), default="auto")
    comment: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class VirtualAccount(Base):
    __tablename__ = "virtual_account"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    balance: Mapped[float] = mapped_column(Float, default=0.0)
    initial_balance: Mapped[float] = mapped_column(Float, default=0.0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
