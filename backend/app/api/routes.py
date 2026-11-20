import pycountry
from fastapi import APIRouter, Depends

from app.api.deps import (
    get_campaign_creator,
    get_offer_service,
    get_stream_editor,
)
from app.schemas.campaign import (
    CreateCampaignRequest,
    CreateCampaignResponse,
)
from app.schemas.editor import (
    AddOfferRequest,
    CampaignOut,
    PinRequest,
    StreamOut,
)
from app.schemas.offer import OfferOut
from app.services.campaign_creator import CampaignCreator
from app.services.offer import OfferService
from app.services.stream_editor import StreamEditor

router = APIRouter()

OFFER_DEP = Depends(get_offer_service)
CREATOR_DEP = Depends(get_campaign_creator)
EDITOR_DEP = Depends(get_stream_editor)


@router.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@router.get("/countries")
async def countries() -> list[str]:
    return sorted(c.alpha_2 for c in pycountry.countries)


@router.get("/offers")
async def offers(
    service: OfferService = OFFER_DEP,
) -> list[OfferOut]:
    return await service.list_offers()


@router.post("/campaigns")
async def create_campaign(
    request: CreateCampaignRequest,
    creator: CampaignCreator = CREATOR_DEP,
) -> CreateCampaignResponse:
    campaign_id, name = await creator.create(request)
    return CreateCampaignResponse(campaign_id=campaign_id, name=name)


@router.get("/offers/search")
async def search_offers(
    q: str = "",
    service: OfferService = OFFER_DEP,
) -> list[OfferOut]:
    return await service.search(q)


@router.post("/editor/campaigns/{keitaro_id}/fetch")
async def editor_fetch(
    keitaro_id: int,
    editor: StreamEditor = EDITOR_DEP,
) -> CampaignOut:
    return await editor.fetch(keitaro_id)


@router.get("/editor/campaigns/{keitaro_id}")
async def editor_view(
    keitaro_id: int,
    editor: StreamEditor = EDITOR_DEP,
) -> CampaignOut:
    return await editor.view_campaign(keitaro_id)


@router.post("/editor/streams/{stream_id}/offers")
async def editor_add_offer(
    stream_id: int,
    request: AddOfferRequest,
    editor: StreamEditor = EDITOR_DEP,
) -> StreamOut:
    return await editor.add_offer(stream_id, request.offer_id)


@router.post("/editor/stream-offers/{link_id}/remove")
async def editor_remove_offer(
    link_id: int,
    editor: StreamEditor = EDITOR_DEP,
) -> StreamOut:
    return await editor.remove_offer(link_id)


@router.post("/editor/stream-offers/{link_id}/bring-back")
async def editor_bring_back(
    link_id: int,
    editor: StreamEditor = EDITOR_DEP,
) -> StreamOut:
    return await editor.bring_back(link_id)


@router.put("/editor/stream-offers/{link_id}/pin")
async def editor_pin(
    link_id: int,
    request: PinRequest,
    editor: StreamEditor = EDITOR_DEP,
) -> StreamOut:
    return await editor.set_pin(link_id, request.pinned)


@router.post("/editor/streams/{stream_id}/push")
async def editor_push(
    stream_id: int,
    editor: StreamEditor = EDITOR_DEP,
) -> StreamOut:
    return await editor.push(stream_id)


@router.post("/editor/streams/{stream_id}/cancel")
async def editor_cancel(
    stream_id: int,
    editor: StreamEditor = EDITOR_DEP,
) -> StreamOut:
    return await editor.cancel(stream_id)
