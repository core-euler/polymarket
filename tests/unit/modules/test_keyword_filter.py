from app.db.models import Market, News
from app.modules.llm_analysis.keyword_filter import KeywordFilter


def _market(question: str, topic: str = "") -> Market:
    return Market(
        polymarket_id="m",
        slug="s",
        title=question,
        question=question,
        topic=topic,
        status="active",
    )


def _news(title: str, content: str = "") -> News:
    return News(
        source_id=1,
        title=title,
        url="https://test/n",
        summary_text="",
        raw_content=content,
        language="en",
        content_hash="h",
        topic="",
        processing_status="new",
    )


def test_returns_top_k_by_overlap_score() -> None:
    f = KeywordFilter(top_k=2, min_score=0.0)
    news = _news("Trump signs new tariff order on China imports")
    markets = [
        _market("Will Trump impose new tariffs on China?"),  # high overlap
        _market("Will the Lakers win the NBA finals?"),  # zero overlap
        _market("Will China retaliate against US tariffs?"),  # medium overlap
    ]

    result = f.rank_candidates(news=news, markets=markets)

    assert len(result) == 2
    assert "tariff" in {*result[0].overlap, *result[1].overlap} or \
           "trump" in {*result[0].overlap, *result[1].overlap}
    assert result[0].score >= result[1].score


def test_filters_below_min_score() -> None:
    f = KeywordFilter(top_k=5, min_score=0.5)
    news = _news("Bitcoin price hits new high")
    markets = [
        _market("Will Bitcoin reach $200k?"),  # decent overlap
        _market("Will the Lakers win the NBA finals?"),  # no overlap
    ]
    result = f.rank_candidates(news=news, markets=markets)
    # Min score 0.5 is high; one or zero should survive
    assert all(c.score >= 0.5 for c in result)


def test_no_overlap_returns_empty() -> None:
    f = KeywordFilter()
    news = _news("Rain forecast for Tuesday")
    markets = [_market("Will SpaceX launch Starship before March?")]
    assert f.rank_candidates(news=news, markets=markets) == []


def test_stopwords_do_not_match() -> None:
    f = KeywordFilter(min_score=0.0)
    news = _news("This will be the result")
    markets = [_market("This is what will happen")]
    # All shared tokens are stopwords → no real overlap
    assert f.rank_candidates(news=news, markets=markets) == []


def test_empty_news_or_market_text() -> None:
    f = KeywordFilter()
    assert f.rank_candidates(news=_news("", ""), markets=[_market("Q")]) == []
    assert f.rank_candidates(news=_news("real news"), markets=[_market("")]) == []
