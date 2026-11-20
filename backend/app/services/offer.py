from app.core.keitaro import KeitaroClient
from app.schemas.offer import OfferOut


class OfferService:
    def __init__(self, keitaro: KeitaroClient) -> None:
        self._keitaro = keitaro

    async def list_offers(self) -> list[OfferOut]:
        data = await self._keitaro.get_offers()
        return [OfferOut(id=int(i["id"]), name=str(i["name"])) for i in data]

    async def search(self, query: str) -> list[OfferOut]:
        needle = query.strip().lower()
        items = await self.list_offers()
        found = [
            i for i in items if needle in str(i.id) or needle in i.name.lower()
        ]
        return found[:20]
