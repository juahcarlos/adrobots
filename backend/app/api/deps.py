from collections.abc import AsyncIterator

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.keitaro import KeitaroClient
from app.services.campaign_creator import CampaignCreator
from app.services.offer import OfferService
from app.services.stream_editor import StreamEditor


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.session_factory() as session:
        yield session


def get_offer_service(request: Request) -> OfferService:
    return OfferService(request.app.state.keitaro)


async def get_campaign_creator(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> CampaignCreator:
    return CampaignCreator(
        session,
        request.app.state.keitaro,
        request.app.state.settings.group_id,
    )


async def get_stream_editor(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> StreamEditor:
    return StreamEditor(session, request.app.state.keitaro)


def get_keitaro(request: Request) -> KeitaroClient:
    return request.app.state.keitaro
