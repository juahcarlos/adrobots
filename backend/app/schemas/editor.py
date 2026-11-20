from pydantic import BaseModel


class AddOfferRequest(BaseModel):
    offer_id: int


class PinRequest(BaseModel):
    pinned: bool


class StreamOfferOut(BaseModel):
    id: int
    offer_id: int
    name: str
    preview_path: str
    share: int
    pinned: bool
    status: str
    is_unpublished: bool
    is_deleted_unpublished: bool


class StreamOut(BaseModel):
    id: int
    keitaro_id: int
    name: str
    position: int
    filters: str
    clicks_today: int
    has_changes: bool
    offers: list[StreamOfferOut]


class CampaignOut(BaseModel):
    id: int
    keitaro_id: int
    name: str
    streams: list[StreamOut]
