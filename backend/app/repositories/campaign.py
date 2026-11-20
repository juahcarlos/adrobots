from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Campaign
from app.repositories.base import BaseRepository


class CampaignRepository(BaseRepository[Campaign]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Campaign)

    async def get_by_keitaro_id(self, keitaro_id: int) -> Campaign | None:
        result = await self._session.execute(
            select(Campaign).where(
                Campaign.keitaro_id == keitaro_id,
                Campaign.status == "synced",
            )
        )
        return result.scalar_one_or_none()
