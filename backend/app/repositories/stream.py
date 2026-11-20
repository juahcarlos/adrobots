from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Stream
from app.repositories.base import BaseRepository


class StreamRepository(BaseRepository[Stream]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Stream)

    async def get_by_keitaro_id(self, keitaro_id: int) -> Stream | None:
        result = await self._session.execute(
            select(Stream).where(Stream.keitaro_id == keitaro_id)
        )
        return result.scalar_one_or_none()

    async def list_by_campaign(self, campaign_id: int) -> list[Stream]:
        result = await self._session.execute(
            select(Stream)
            .where(Stream.campaign_id == campaign_id)
            .order_by(Stream.position)
        )
        return list(result.scalars().all())
