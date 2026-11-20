import httpx
import pytest

from app.core.keitaro import KeitaroClient, KeitaroError


def make_client(handler) -> KeitaroClient:
    client = KeitaroClient("http://keitaro.test/api", "token", timeout=5)
    client._client = httpx.AsyncClient(
        base_url="http://keitaro.test/api",
        transport=httpx.MockTransport(handler),
    )
    return client


async def test_error_body_passed_without_changes() -> None:
    body = '{"error":"Alias already exists","details":["a","b"]}\n'

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(409, text=body)

    client = make_client(handler)
    with pytest.raises(KeitaroError) as exc:
        await client.post("/campaigns", {"name": "x"})
    assert str(exc.value) == body
    assert exc.value.status_code == 409
    await client.aclose()


async def test_error_with_empty_body_falls_back_to_status() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    client = make_client(handler)
    with pytest.raises(KeitaroError) as exc:
        await client.get("/offers")
    assert "500" in str(exc.value)
    assert exc.value.status_code == 500
    await client.aclose()


async def test_not_json_response_is_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>")

    client = make_client(handler)
    with pytest.raises(KeitaroError):
        await client.get("/offers")
    await client.aclose()


async def test_delete_accepts_empty_body() -> None:
    seen: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path))
        return httpx.Response(200)

    client = make_client(handler)
    assert await client.delete("/streams/5") is None
    assert seen == [("DELETE", "/api/streams/5")]
    await client.aclose()


async def test_delete_error_keeps_original_text() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="Stream not found")

    client = make_client(handler)
    with pytest.raises(KeitaroError) as exc:
        await client.delete("/streams/5")
    assert str(exc.value) == "Stream not found"
    await client.aclose()
