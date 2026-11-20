from pydantic import BaseModel, Field


class CreateCampaignRequest(BaseModel):
    name: str = Field(min_length=1)
    geo: str = Field(min_length=2, max_length=2)
    offer_id: int


class CreateCampaignResponse(BaseModel):
    campaign_id: int
    name: str


class ErrorResponse(BaseModel):
    step: str | None = None
    source: str | None = None
    error: str
    campaign_id: int | None = None
