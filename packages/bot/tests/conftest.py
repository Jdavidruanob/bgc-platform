from collections.abc import AsyncIterator

import httpx
import pytest
from coop_bot.api.cliente import ApiClient
from coop_contracts.mock_server import app

MOCK_TOKEN = "mock-secret"


@pytest.fixture
def mock_transport() -> httpx.ASGITransport:
    return httpx.ASGITransport(app=app)


@pytest.fixture
async def api_client(mock_transport: httpx.ASGITransport) -> AsyncIterator[ApiClient]:
    client = ApiClient(
        base_url="http://mock",
        token=MOCK_TOKEN,
        transport=mock_transport,
    )
    await client.resetear_mock()
    yield client
    await client.resetear_mock()
    await client.aclose()
