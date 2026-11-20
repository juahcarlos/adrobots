from collections.abc import Collection

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import StreamOffer
from app.repositories.base import BaseRepository


class StreamOfferRepository(BaseRepository[StreamOffer]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, StreamOffer)

    async def get_pair(
        self, stream_id: int, offer_id: int
    ) -> StreamOffer | None:
        result = await self._session.execute(
            select(StreamOffer).where(
                StreamOffer.stream_id == stream_id,
                StreamOffer.offer_id == offer_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_by_streams(
        self, stream_ids: Collection[int]
    ) -> list[StreamOffer]:
        if not stream_ids:
            return []
        result = await self._session.execute(
            select(StreamOffer)
            .where(StreamOffer.stream_id.in_(stream_ids))
            .order_by(StreamOffer.id)
        )
        return list(result.scalars().all())
