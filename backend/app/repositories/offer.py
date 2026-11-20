from collections.abc import Collection

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Offer
from app.repositories.base import BaseRepository


class OfferRepository(BaseRepository[Offer]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Offer)

    async def get_by_keitaro_id(self, keitaro_id: int) -> Offer | None:
        result = await self._session.execute(
            select(Offer).where(Offer.keitaro_id == keitaro_id)
        )
        return result.scalar_one_or_none()

    async def list_by_ids(self, ids: Collection[int]) -> list[Offer]:
        if not ids:
            return []
        result = await self._session.execute(
            select(Offer).where(Offer.id.in_(ids))
        )
        return list(result.scalars().all())

    async def list_by_keitaro_ids(self, ids: Collection[int]) -> list[Offer]:
        if not ids:
            return []
        result = await self._session.execute(
            select(Offer).where(Offer.keitaro_id.in_(ids))
        )
        return list(result.scalars().all())
