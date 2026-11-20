import asyncio
import logging
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_PATH = __file__


class KeitaroError(Exception):
    """Ошибка API Keitaro: текст берётся из ответа Keitaro без изменений."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class KeitaroClient:
    def __init__(self, base_url: str, api_token: str, timeout: float) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers={"Api-Key": api_token},
            timeout=timeout,
        )
        self._offers_cache: list[dict] | None = None
        self._offers_cache_at = 0.0
        self._offers_lock = asyncio.Lock()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def get(self, path: str) -> Any:
        return await self._request("get", path)

    async def get_offers(self) -> list[dict]:
        if (
            self._offers_cache is not None
            and time.monotonic() - self._offers_cache_at < 60
        ):
            return self._offers_cache

        async with self._offers_lock:
            if (
                self._offers_cache is not None
                and time.monotonic() - self._offers_cache_at < 60
            ):
                return self._offers_cache

            self._offers_cache = await self.get("/offers")
            self._offers_cache_at = time.monotonic()
            return self._offers_cache

    async def post(self, path: str, payload: dict) -> Any:
        return await self._request("post", path, payload)

    async def put(self, path: str, payload: dict) -> Any:
        return await self._request("put", path, payload)

    async def delete(self, path: str) -> Any:
        # Keitaro на DELETE может вернуть пустое тело — это не ошибка.
        return await self._request("delete", path, allow_empty=True)

    async def _request(
        self,
        method: str,
        path: str,
        payload: dict | None = None,
        allow_empty: bool = False,
    ) -> Any:
        try:
            if payload is None:
                response = await self._client.request(method, path)
            else:
                response = await self._client.request(
                    method, path, json=payload
                )
        except httpx.HTTPError as e:
            logger.error(
                "\n\n !!! --- ERROR --- !!! %s %s.%s %s e=%s\n\n",
                _PATH,
                "KeitaroClient",
                method,
                "Keitaro недоступен",
                e,
            )
            raise KeitaroError(f"Keitaro недоступен: {e}") from e
        return self._handle(response, allow_empty=allow_empty)

    @staticmethod
    def _handle(response: httpx.Response, allow_empty: bool = False) -> Any:
        if response.is_error:
            logger.error(
                "\n\n !!! --- ERROR --- !!! %s %s.%s %s status=%s text=%s\n\n",
                _PATH,
                "KeitaroClient",
                "_handle",
                "Keitaro вернул ошибку",
                response.status_code,
                response.text,
            )
            body = response.text
            raise KeitaroError(
                body
                if body.strip()
                else f"Keitaro вернул ошибку {response.status_code}",
                status_code=response.status_code,
            )
        if allow_empty and not response.content.strip():
            return None
        try:
            return response.json()
        except ValueError as e:
            logger.error(
                "\n\n !!! --- ERROR --- !!! %s %s.%s %s e=%s text=%s\n\n",
                _PATH,
                "KeitaroClient",
                "_handle",
                "ответ Keitaro не JSON",
                e,
                response.text,
            )
            raise KeitaroError("Некорректный ответ Keitaro") from e
