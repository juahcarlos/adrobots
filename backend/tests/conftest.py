import os

os.environ.setdefault("KEITARO_API_URL", "http://keitaro.test/api")
os.environ.setdefault("KEITARO_API_TOKEN", "test-token")
os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://u:p@localhost:5432/test"
)
os.environ.setdefault("GROUP_ID", "10332")
os.environ.setdefault("LOG_LEVEL", "INFO")

from collections.abc import AsyncIterator, Callable
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_campaign_creator, get_keitaro
from app.api.errors import register_exception_handlers
from app.api.routes import router
from app.core.keitaro import KeitaroError


class FakeKeitaro:
    """Подмена клиента Keitaro: ответы и ошибки из словарей."""

    def __init__(self) -> None:
        self.get_responses: dict[str, object] = {}
        self.post_queues: dict[str, list[object]] = {}
        self.get_calls: list[str] = []
        self.post_calls: list[tuple[str, dict]] = []
        self.put_calls: list[tuple[str, dict]] = []
        self.delete_calls: list[str] = []
        self.delete_errors: dict[str, Exception] = {}

    async def get(self, path: str) -> object:
        self.get_calls.append(path)
        response = self.get_responses[path]
        if isinstance(response, Exception):
            raise response
        return response

    async def post(self, path: str, payload: dict) -> object:
        self.post_calls.append((path, payload))
        item = self.post_queues[path].pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    async def put(self, path: str, payload: dict) -> object:
        self.put_calls.append((path, payload))
        return {}

    async def delete(self, path: str) -> None:
        self.delete_calls.append(path)
        error = self.delete_errors.get(path)
        if error is not None:
            raise error

    async def get_offers(self) -> object:
        return await self.get("/offers")


class FakeRepo:
    def __init__(self, existing: object | None = None) -> None:
        self.added: list[object] = []
        self._existing = existing

    async def add(self, instance: object) -> object:
        instance.id = len(self.added) + 1
        self.added.append(instance)
        return instance

    async def get_by_keitaro_id(self, keitaro_id: int) -> object | None:
        return self._existing


@pytest.fixture
def fake_keitaro() -> FakeKeitaro:
    return FakeKeitaro()


@pytest.fixture
def session() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    app = FastAPI()
    app.include_router(router)
    register_exception_handlers(app)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


def override_dependencies(client: AsyncClient, **overrides: object) -> None:
    app = client._transport.app  # type: ignore[attr-defined]
    for name, obj in overrides.items():
        app.dependency_overrides[_OVERRIDABLE[name]] = _provide(obj)


_OVERRIDABLE: dict[str, Callable] = {
    "keitaro": get_keitaro,
    "campaign_creator": get_campaign_creator,
}


def _provide(obj: object) -> Callable[[], object]:
    return lambda: obj


__all__ = [
    "FakeKeitaro",
    "FakeRepo",
    "KeitaroError",
    "override_dependencies",
]
