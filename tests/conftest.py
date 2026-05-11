from collections.abc import AsyncGenerator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.router import api_router


@pytest.fixture
def api_app() -> FastAPI:
    app = FastAPI()
    app.include_router(api_router)
    return app


@pytest.fixture
def client(api_app: FastAPI) -> AsyncGenerator[TestClient, None]:
    with TestClient(api_app) as test_client:
        yield test_client

