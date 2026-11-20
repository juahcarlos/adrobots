from pydantic import BaseModel


class OfferOut(BaseModel):
    id: int
    name: str
