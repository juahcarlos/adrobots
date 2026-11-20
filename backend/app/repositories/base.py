from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Base


class BaseRepository[ModelT: Base]:
    def __init__(self, session: AsyncSession, model: type[ModelT]) -> None:
        self._session = session
        self._model = model

    async def get_by_id(self, id_: int) -> ModelT | None:
        return await self._session.get(self._model, id_)

    async def list(self) -> list[ModelT]:
        result = await self._session.execute(select(self._model))
        return list(result.scalars().all())

    async def add(self, instance: ModelT) -> ModelT:
        self._session.add(instance)
        await self._session.flush()
        return instance

    async def update(self, instance: ModelT) -> ModelT:
        self._session.add(instance)
        await self._session.flush()
        return instance

    async def delete(self, instance: ModelT) -> None:
        await self._session.delete(instance)
        await self._session.flush()
