from app.workers.tasks import pipeline


class _SessionContextManager:
    def __init__(self, session: object) -> None:
        self.session = session

    async def __aenter__(self) -> object:
        return self.session

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False


def _session_factory(session: object):
    def factory():
        return _SessionContextManager(session)

    return factory


class _FakeMarketModule:
    def __init__(self, expected_session: object) -> None:
        self.expected_session = expected_session
        self.sync_called = False
        self.snapshot_called = False

    async def sync_markets(self, session) -> int:
        assert session is self.expected_session
        self.sync_called = True
        return 3

    async def capture_snapshots(self, session) -> int:
        assert session is self.expected_session
        self.snapshot_called = True
        return 5


class _FakeNewsModule:
    def __init__(self, expected_session: object) -> None:
        self.expected_session = expected_session
        self.ingest_called = False

    async def ingest_news(self, session) -> int:
        assert session is self.expected_session
        self.ingest_called = True
        return 4


class _FakeSignalModule:
    def __init__(self, expected_session: object) -> None:
        self.expected_session = expected_session
        self.generate_called = False

    async def generate_signals(self, session) -> int:
        assert session is self.expected_session
        self.generate_called = True
        return 6


class _FakeLLMModule:
    def __init__(self, expected_session: object) -> None:
        self.expected_session = expected_session
        self.called = False

    async def analyze_pending_news(self, session) -> int:
        assert session is self.expected_session
        self.called = True
        return 11


class _FakePaperModule:
    def __init__(self, expected_session: object) -> None:
        self.expected_session = expected_session
        self.open_called = False
        self.monitor_called = False

    async def open_eligible_trades(self, session) -> int:
        assert session is self.expected_session
        self.open_called = True
        return 2

    async def monitor_open_trades(self, session) -> int:
        assert session is self.expected_session
        self.monitor_called = True
        return 3


class _FakeReviewModule:
    def __init__(self, expected_session: object) -> None:
        self.expected_session = expected_session
        self.called = False

    async def create_auto_reviews(self, session) -> int:
        assert session is self.expected_session
        self.called = True
        return 1


class _FakeAntipatternModule:
    def __init__(self, expected_session: object) -> None:
        self.expected_session = expected_session
        self.called = False

    async def detect_for_recent_signals(self, session) -> int:
        assert session is self.expected_session
        self.called = True
        return 2


class _FakeAnalyticsModule:
    def __init__(self, expected_session: object) -> None:
        self.expected_session = expected_session
        self.called = False

    async def refresh_aggregates(self, session) -> int:
        assert session is self.expected_session
        self.called = True
        return 5


async def test_run_market_refresh_job_calls_market_module() -> None:
    session = object()
    module = _FakeMarketModule(expected_session=session)

    processed = await pipeline.run_market_refresh_job(
        session_factory=_session_factory(session),
        module_factory=lambda: module,
    )

    assert processed == 3
    assert module.sync_called is True


async def test_run_market_snapshot_job_calls_market_module() -> None:
    session = object()
    module = _FakeMarketModule(expected_session=session)

    processed = await pipeline.run_market_snapshot_job(
        session_factory=_session_factory(session),
        module_factory=lambda: module,
    )

    assert processed == 5
    assert module.snapshot_called is True


def test_market_refresh_task_uses_sync_runner(monkeypatch) -> None:
    monkeypatch.setattr(pipeline, "run_market_refresh_job_sync", lambda: 7)
    result = pipeline.market_refresh_task()
    assert result == "market_refresh_task completed: 7"


def test_market_snapshot_task_uses_sync_runner(monkeypatch) -> None:
    monkeypatch.setattr(pipeline, "run_market_snapshot_job_sync", lambda: 9)
    result = pipeline.market_snapshot_task()
    assert result == "market_snapshot_task completed: 9"


async def test_run_news_ingestion_job_calls_news_module() -> None:
    session = object()
    module = _FakeNewsModule(expected_session=session)

    processed = await pipeline.run_news_ingestion_job(
        session_factory=_session_factory(session),
        module_factory=lambda: module,
    )

    assert processed == 4
    assert module.ingest_called is True


def test_news_ingestion_task_uses_sync_runner(monkeypatch) -> None:
    monkeypatch.setattr(pipeline, "run_news_ingestion_job_sync", lambda: 12)
    result = pipeline.news_ingestion_task()
    assert result == "news_ingestion_task completed: 12"


async def test_run_signal_generation_job_calls_signal_module() -> None:
    session = object()
    module = _FakeSignalModule(expected_session=session)

    processed = await pipeline.run_signal_generation_job(
        session_factory=_session_factory(session),
        module_factory=lambda: module,
    )

    assert processed == 6
    assert module.generate_called is True


def test_signal_generation_task_uses_sync_runner(monkeypatch) -> None:
    monkeypatch.setattr(pipeline, "run_signal_generation_job_sync", lambda: 15)
    monkeypatch.setattr(
        pipeline.paper_trade_monitoring_task, "delay", lambda *a, **k: None
    )
    result = pipeline.signal_generation_task()
    assert result == "signal_generation_task completed: 15"


def test_signal_generation_task_chains_paper_trade_monitor(monkeypatch) -> None:
    chained: list[bool] = []
    monkeypatch.setattr(pipeline, "run_signal_generation_job_sync", lambda: 7)
    monkeypatch.setattr(
        pipeline.paper_trade_monitoring_task, "delay",
        lambda *a, **k: chained.append(True),
    )
    pipeline.signal_generation_task()
    assert chained == [True]


def test_signal_generation_task_skips_chain_when_zero(monkeypatch) -> None:
    chained: list[bool] = []
    monkeypatch.setattr(pipeline, "run_signal_generation_job_sync", lambda: 0)
    monkeypatch.setattr(
        pipeline.paper_trade_monitoring_task, "delay",
        lambda *a, **k: chained.append(True),
    )
    pipeline.signal_generation_task()
    assert chained == []


async def test_run_news_analysis_job_calls_llm_module() -> None:
    session = object()
    module = _FakeLLMModule(expected_session=session)

    processed = await pipeline.run_news_analysis_job(
        session_factory=_session_factory(session),
        module_factory=lambda: module,
    )

    assert processed == 11
    assert module.called is True


def test_news_analysis_task_uses_sync_runner(monkeypatch) -> None:
    monkeypatch.setattr(pipeline, "run_news_analysis_job_sync", lambda: 11)
    monkeypatch.setattr(pipeline, "count_pending_news_sync", lambda: 0)
    monkeypatch.setattr(
        pipeline.signal_generation_task, "delay", lambda *a, **k: None
    )
    monkeypatch.setattr(
        pipeline.news_analysis_task, "delay", lambda *a, **k: None
    )
    result = pipeline.news_analysis_task()
    assert result == "news_analysis_task completed: 11"


def test_news_analysis_task_chains_signal_generation(monkeypatch) -> None:
    chained: list[bool] = []
    monkeypatch.setattr(pipeline, "run_news_analysis_job_sync", lambda: 4)
    monkeypatch.setattr(pipeline, "count_pending_news_sync", lambda: 0)
    monkeypatch.setattr(
        pipeline.signal_generation_task, "delay",
        lambda *a, **k: chained.append(True),
    )
    monkeypatch.setattr(
        pipeline.news_analysis_task, "delay", lambda *a, **k: None
    )
    pipeline.news_analysis_task()
    assert chained == [True]


def test_news_analysis_task_skips_chain_when_zero(monkeypatch) -> None:
    chained: list[bool] = []
    monkeypatch.setattr(pipeline, "run_news_analysis_job_sync", lambda: 0)
    monkeypatch.setattr(pipeline, "count_pending_news_sync", lambda: 0)
    monkeypatch.setattr(
        pipeline.signal_generation_task, "delay",
        lambda *a, **k: chained.append(True),
    )
    monkeypatch.setattr(
        pipeline.news_analysis_task, "delay", lambda *a, **k: None
    )
    pipeline.news_analysis_task()
    assert chained == []


def test_news_analysis_task_self_chains_when_pending_remains(monkeypatch) -> None:
    self_chained: list[bool] = []
    monkeypatch.setattr(pipeline, "run_news_analysis_job_sync", lambda: 5)
    monkeypatch.setattr(pipeline, "count_pending_news_sync", lambda: 17)
    monkeypatch.setattr(
        pipeline.signal_generation_task, "delay", lambda *a, **k: None
    )
    monkeypatch.setattr(
        pipeline.news_analysis_task, "delay",
        lambda *a, **k: self_chained.append(True),
    )
    pipeline.news_analysis_task()
    assert self_chained == [True]


def test_news_analysis_task_no_self_chain_when_queue_empty(monkeypatch) -> None:
    self_chained: list[bool] = []
    monkeypatch.setattr(pipeline, "run_news_analysis_job_sync", lambda: 5)
    monkeypatch.setattr(pipeline, "count_pending_news_sync", lambda: 0)
    monkeypatch.setattr(
        pipeline.signal_generation_task, "delay", lambda *a, **k: None
    )
    monkeypatch.setattr(
        pipeline.news_analysis_task, "delay",
        lambda *a, **k: self_chained.append(True),
    )
    pipeline.news_analysis_task()
    assert self_chained == []


async def test_run_paper_trade_monitoring_job_calls_paper_module() -> None:
    session = object()
    module = _FakePaperModule(expected_session=session)

    processed = await pipeline.run_paper_trade_monitoring_job(
        session_factory=_session_factory(session),
        module_factory=lambda: module,
    )

    assert processed == 5
    assert module.open_called is True
    assert module.monitor_called is True


def test_paper_trade_monitoring_task_uses_sync_runner(monkeypatch) -> None:
    monkeypatch.setattr(pipeline, "run_paper_trade_monitoring_job_sync", lambda: 5)
    result = pipeline.paper_trade_monitoring_task()
    assert result == "paper_trade_monitoring_task completed: 5"


async def test_run_auto_review_job_calls_review_and_antipattern_modules() -> None:
    session = object()
    review_module = _FakeReviewModule(expected_session=session)
    anti_module = _FakeAntipatternModule(expected_session=session)

    processed = await pipeline.run_auto_review_job(
        session_factory=_session_factory(session),
        review_module_factory=lambda: review_module,
        antipattern_module_factory=lambda: anti_module,
    )

    assert processed == 3
    assert review_module.called is True
    assert anti_module.called is True


def test_auto_review_task_uses_sync_runner(monkeypatch) -> None:
    monkeypatch.setattr(pipeline, "run_auto_review_job_sync", lambda: 3)
    result = pipeline.auto_review_task()
    assert result == "auto_review_task completed: 3"


async def test_run_analytics_refresh_job_calls_analytics_module() -> None:
    session = object()
    module = _FakeAnalyticsModule(expected_session=session)

    processed = await pipeline.run_analytics_refresh_job(
        session_factory=_session_factory(session),
        module_factory=lambda: module,
    )

    assert processed == 5
    assert module.called is True


def test_analytics_refresh_task_uses_sync_runner(monkeypatch) -> None:
    monkeypatch.setattr(pipeline, "run_analytics_refresh_job_sync", lambda: 5)
    result = pipeline.analytics_refresh_task()
    assert result == "analytics_refresh_task completed: 5"
