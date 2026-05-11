from app.db.models import Market, News
from app.modules.llm_analysis.relevance_checker import (
    CometRelevanceChecker,
    NullRelevanceChecker,
)


class _FakeCometClient:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.last_prompt: str | None = None

    async def analyze_text(self, prompt: str) -> dict:
        self.last_prompt = prompt
        return self.payload


def _content(text: str) -> dict:
    return {"choices": [{"message": {"content": text}}]}


async def test_null_checker_passes_through() -> None:
    checker = NullRelevanceChecker()
    result = await checker.check(news=News(title="n"), market=Market(question="q"))
    assert result.relevant is True
    assert result.score == 1.0


async def test_parses_clean_json() -> None:
    client = _FakeCometClient(_content('{"relevant": true, "score": 0.83}'))
    checker = CometRelevanceChecker(client=client)
    result = await checker.check(news=News(title="n"), market=Market(question="q"))
    assert result.relevant is True
    assert result.score == 0.83


async def test_parses_fenced_json() -> None:
    client = _FakeCometClient(_content('```json\n{"relevant": false, "score": 0.1}\n```'))
    checker = CometRelevanceChecker(client=client)
    result = await checker.check(news=News(title="n"), market=Market(question="q"))
    assert result.relevant is False
    assert result.score == 0.1


async def test_clamps_out_of_range_score() -> None:
    client = _FakeCometClient(_content('{"relevant": true, "score": 1.7}'))
    checker = CometRelevanceChecker(client=client)
    result = await checker.check(news=News(title="n"), market=Market(question="q"))
    assert result.score == 1.0


async def test_garbage_response_is_not_relevant() -> None:
    client = _FakeCometClient(_content("nonsense without json"))
    checker = CometRelevanceChecker(client=client)
    result = await checker.check(news=News(title="n"), market=Market(question="q"))
    assert result.relevant is False
    assert result.score == 0.0
