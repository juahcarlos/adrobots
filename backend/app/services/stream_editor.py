import logging
from collections.abc import Iterable
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.keitaro import KeitaroClient
from app.models import Campaign, Offer, Stream, StreamOffer
from app.repositories.campaign import CampaignRepository
from app.repositories.offer import OfferRepository
from app.repositories.stream import StreamRepository
from app.repositories.stream_offer import StreamOfferRepository
from app.schemas.editor import CampaignOut, StreamOfferOut, StreamOut
from app.services.exceptions import (
    CampaignServiceError,
    NotFoundError,
    ValidationError,
)

logger = logging.getLogger(__name__)

_PATH = __file__


class StreamEditor:
    def __init__(
        self,
        session: AsyncSession,
        keitaro: KeitaroClient,
    ) -> None:
        self._session = session
        self._keitaro = keitaro
        self._campaigns = CampaignRepository(session)
        self._streams = StreamRepository(session)
        self._offers = OfferRepository(session)
        self._links = StreamOfferRepository(session)
        self._catalog: dict[int, dict[str, Any]] | None = None

    async def fetch(self, campaign_keitaro_id: int) -> CampaignOut:
        campaign = await self._ensure_campaign(campaign_keitaro_id)

        data = await self._keitaro.get(
            f"/campaigns/{campaign_keitaro_id}/streams"
        )

        rows: list = []
        offset = 0
        while True:
            report = await self._keitaro.post(
                "/report/build",
                {
                    "dimensions": ["stream"],
                    "measures": ["clicks"],
                    "filters": {
                        "AND": [
                            {
                                "expression": campaign_keitaro_id,
                                "name": "campaign_id",
                                "operator": "EQUALS",
                            }
                        ]
                    },
                    "range": {
                        "interval": "today",
                        "timezone": "Europe/Moscow",
                    },
                    "limit": 100,
                    "offset": offset,
                },
            )
            page = report.get("rows") or []
            rows.extend(page)
            offset += len(page)

            total = report.get("total")
            if (
                not page
                or len(page) < 100
                or (total is not None and len(rows) >= int(total))
            ):
                break

        clicks = {int(row["stream_id"]): int(row["clicks"]) for row in rows}

        synced: list[tuple[Stream, list[dict[str, Any]]]] = []
        for item in data:
            stream = await self._upsert_stream(
                campaign.id, item, clicks.get(int(item["id"]), 0)
            )
            synced.append((stream, item.get("offers") or []))

        # Связи и офферы всех потоков — по одному запросу на всю кампанию.
        offers_by_kt = await self._ensure_offers(
            int(o["offer_id"]) for _, kt_offers in synced for o in kt_offers
        )
        links_by_stream = await self._load_links_by_stream(
            [stream.id for stream, _ in synced]
        )
        for stream, kt_offers in synced:
            await self._sync_links(
                stream,
                kt_offers,
                links=links_by_stream.get(stream.id, []),
                offers_by_kt=offers_by_kt,
            )

        await self._commit("fetch")
        return await self._campaign_view(campaign)

    async def view_campaign(self, campaign_keitaro_id: int) -> CampaignOut:
        campaign = await self._campaigns.get_by_keitaro_id(campaign_keitaro_id)
        if campaign is None:
            raise NotFoundError("Кампания не загружена, сначала Fetch Streams")
        return await self._campaign_view(campaign)

    async def add_offer(
        self, stream_id: int, offer_keitaro_id: int
    ) -> StreamOut:
        stream = await self._get_stream(stream_id)
        offer = await self._ensure_offer(offer_keitaro_id)
        link = await self._links.get_pair(stream.id, offer.id)
        if link is not None and link.status == "active":
            raise ValidationError("Оффер уже есть в потоке")
        if link is None:
            await self._links.add(
                StreamOffer(
                    stream_id=stream.id,
                    offer_id=offer.id,
                    share=0,
                    pinned=False,
                    status="active",
                    is_unpublished=True,
                    is_deleted_unpublished=False,
                )
            )
        else:
            self._restore(link)
        await self._rebalance(stream.id)
        await self._commit("add_offer")
        return await self._stream_view(stream)

    async def remove_offer(self, link_id: int) -> StreamOut:
        link = await self._get_link(link_id)
        if link.status != "active":
            raise ValidationError("Оффер уже удалён")
        stream_id = link.stream_id
        if link.is_unpublished:
            await self._links.delete(link)
        else:
            link.status = "removed"
            link.share = 0
            link.pinned = False
            link.is_deleted_unpublished = True
        await self._rebalance(stream_id)
        await self._commit("remove_offer")
        return await self._stream_view(await self._get_stream(stream_id))

    async def bring_back(self, link_id: int) -> StreamOut:
        link = await self._get_link(link_id)
        if link.status != "removed":
            raise ValidationError("Оффер не удалён")
        self._restore(link)
        await self._rebalance(link.stream_id)
        await self._commit("bring_back")
        stream = await self._get_stream(link.stream_id)
        return await self._stream_view(stream)

    async def set_pin(self, link_id: int, pinned: bool) -> StreamOut:
        link = await self._get_link(link_id)
        if link.status != "active":
            raise ValidationError("Нельзя закрепить удалённый оффер")
        link.pinned = pinned
        await self._commit("set_pin")
        stream = await self._get_stream(link.stream_id)
        return await self._stream_view(stream)

    async def push(self, stream_id: int) -> StreamOut:
        stream = await self._get_stream(stream_id)
        links = await self._links.list_by_streams([stream_id])
        active = [link for link in links if link.status == "active"]
        self._check_total(active)
        offers_by_id = await self._offers_by_id(
            link.offer_id for link in links
        )
        offers = []
        for link in active:
            offer = offers_by_id.get(link.offer_id)
            if offer is None:
                raise NotFoundError(f"Оффер id={link.offer_id} не в БД")
            offers.append(
                {
                    "offer_id": offer.keitaro_id,
                    "share": link.share,
                    "state": "active",
                }
            )
        await self._keitaro.put(
            f"/streams/{stream.keitaro_id}", {"offers": offers}
        )
        for link in links:
            link.is_unpublished = False
            link.is_deleted_unpublished = False
        await self._commit("push")
        return self._build_stream_view(stream, links, offers_by_id)

    async def cancel(self, stream_id: int) -> StreamOut:
        stream = await self._get_stream(stream_id)
        if stream.keitaro_id is None:
            raise ValidationError("Поток ещё не создан в Keitaro")
        campaign = await self._campaigns.get_by_id(stream.campaign_id)
        if campaign is None:
            raise NotFoundError("Кампания потока не найдена в БД")
        data = await self._keitaro.get(
            f"/campaigns/{campaign.keitaro_id}/streams"
        )
        item = next(
            (i for i in data if int(i["id"]) == stream.keitaro_id), None
        )
        if item is None:
            raise NotFoundError("Поток не найден в Keitaro")
        await self._sync_links(stream, item.get("offers") or [])
        await self._commit("cancel")
        return await self._stream_view(stream)

    async def _commit(self, method: str) -> None:
        try:
            await self._session.commit()
        except Exception as e:
            await self._session.rollback()
            logger.error(
                "\n\n !!! --- ERROR --- !!! %s %s.%s %s e=%s\n\n",
                _PATH,
                "StreamEditor",
                method,
                "не удалось сохранить в БД",
                e,
            )
            raise CampaignServiceError(step="db", error=str(e)) from e

    async def _get_stream(self, stream_id: int) -> Stream:
        stream = await self._streams.get_by_id(stream_id)
        if stream is None:
            raise NotFoundError(f"Поток id={stream_id} не найден")
        return stream

    async def _get_link(self, link_id: int) -> StreamOffer:
        link = await self._links.get_by_id(link_id)
        if link is None:
            raise NotFoundError(f"Оффер в потоке id={link_id} не найден")
        return link

    async def _load_catalog(self) -> dict[int, dict[str, Any]]:
        if self._catalog is None:
            data = await self._keitaro.get("/offers")
            self._catalog = {int(i["id"]): i for i in data}
        return self._catalog

    async def _ensure_offer(self, keitaro_id: int) -> Offer:
        return (await self._ensure_offers([keitaro_id]))[keitaro_id]

    async def _ensure_offers(
        self, keitaro_ids: Iterable[int]
    ) -> dict[int, Offer]:
        """Офферы по keitaro_id: один IN-запрос, недостающие — из каталога."""
        wanted = set(keitaro_ids)
        if not wanted:
            return {}
        found = {
            offer.keitaro_id: offer
            for offer in await self._offers.list_by_keitaro_ids(wanted)
        }
        missing = wanted - found.keys()
        if missing:
            catalog = await self._load_catalog()
            for keitaro_id in sorted(missing):
                info = catalog.get(keitaro_id)
                if info is None:
                    raise NotFoundError(
                        f"Оффер с id={keitaro_id} не найден в Keitaro"
                    )
                found[keitaro_id] = await self._offers.add(
                    Offer(
                        keitaro_id=keitaro_id,
                        name=str(info.get("name") or ""),
                        preview_path=str(info.get("preview_path") or ""),
                    )
                )
        return found

    async def _offers_by_id(
        self, offer_ids: Iterable[int]
    ) -> dict[int, Offer]:
        ids = set(offer_ids)
        if not ids:
            return {}
        return {o.id: o for o in await self._offers.list_by_ids(ids)}

    async def _load_links_by_stream(
        self, stream_ids: list[int]
    ) -> dict[int, list[StreamOffer]]:
        grouped: dict[int, list[StreamOffer]] = {}
        if not stream_ids:
            return grouped
        for link in await self._links.list_by_streams(stream_ids):
            grouped.setdefault(link.stream_id, []).append(link)
        return grouped

    async def _ensure_campaign(self, keitaro_id: int) -> Campaign:
        campaign = await self._campaigns.get_by_keitaro_id(keitaro_id)
        if campaign is not None:
            return campaign
        data = await self._keitaro.get(f"/campaigns/{keitaro_id}")
        return await self._campaigns.add(
            Campaign(
                keitaro_id=keitaro_id,
                name=str(data.get("name") or ""),
                alias=str(data.get("alias") or ""),
                domain_id=int(data["domain_id"]),
                group_id=str(data.get("group_id") or ""),
                traffic_source_id=int(data["traffic_source_id"]),
                status="synced",
            )
        )

    async def _upsert_stream(
        self, campaign_id: int, item: dict[str, Any], clicks_today: int
    ) -> Stream:
        keitaro_id = int(item["id"])
        name = str(item.get("name") or "")
        position = int(item.get("position") or 0)
        # Поток без офферов нужен в редакторе только как строка списка:
        # его фильтры, редиректы и прочие настройки не разбираем.
        has_offers = bool(item.get("offers"))

        type_ = schema = action_type = filters = ""
        if has_offers:
            type_ = str(item.get("type") or "")
            schema = str(item.get("schema") or "")
            action_type = str(item.get("action_type") or "")
            filters = ", ".join(
                str(f.get("name")) for f in item.get("filters") or []
            )

        stream = await self._streams.get_by_keitaro_id(keitaro_id)
        if stream is None:
            return await self._streams.add(
                Stream(
                    keitaro_id=keitaro_id,
                    campaign_id=campaign_id,
                    name=name,
                    type=type_,
                    schema=schema,
                    action_type=action_type,
                    position=position,
                    filters=filters,
                    clicks_today=clicks_today,
                )
            )
        stream.name = name
        stream.position = position
        stream.clicks_today = clicks_today
        if has_offers:
            stream.type = type_
            stream.schema = schema
            stream.action_type = action_type
            stream.filters = filters
        return stream

    async def _sync_links(
        self,
        stream: Stream,
        kt_offers: list[dict[str, Any]],
        links: list[StreamOffer] | None = None,
        offers_by_kt: dict[int, Offer] | None = None,
    ) -> None:
        if links is None:
            links = await self._links.list_by_streams([stream.id])
        if offers_by_kt is None:
            offers_by_kt = await self._ensure_offers(
                int(item["offer_id"]) for item in kt_offers
            )
        by_offer = {link.offer_id: link for link in links}
        kt_ids: set[int] = set()
        for item in kt_offers:
            offer = offers_by_kt[int(item["offer_id"])]
            kt_ids.add(offer.id)
            share = int(item["share"])
            link = by_offer.get(offer.id)
            if link is None:
                by_offer[offer.id] = await self._links.add(
                    StreamOffer(
                        stream_id=stream.id,
                        offer_id=offer.id,
                        share=share,
                        pinned=False,
                        status="active",
                        is_unpublished=False,
                        is_deleted_unpublished=False,
                    )
                )
                continue
            link.share = share
            link.status = "active"
            link.is_unpublished = False
            link.is_deleted_unpublished = False
        for link in links:
            if link.offer_id in kt_ids:
                continue
            if link.status == "active" and link.is_unpublished:
                await self._links.delete(link)
                continue
            link.status = "removed"
            link.share = 0
            link.pinned = False
            link.is_unpublished = False
            link.is_deleted_unpublished = False

    @staticmethod
    def _restore(link: StreamOffer) -> None:
        link.is_unpublished = not link.is_deleted_unpublished
        link.status = "active"
        link.is_deleted_unpublished = False

    @staticmethod
    def _check_total(active: list[StreamOffer]) -> None:
        """Публикация возможна только при сумме долей активных = 100%."""
        if not active:
            return
        total = sum(link.share for link in active)
        if total == 100:
            return
        if all(link.pinned for link in active):
            raise ValidationError(
                "Все офферы закреплены: сумма закреплённых долей должна "
                f"быть 100%, сейчас {total}%"
            )
        raise ValidationError(f"Сумма долей должна быть 100, сейчас {total}")

    async def _rebalance(self, stream_id: int) -> None:
        links = await self._links.list_by_streams([stream_id])
        active = [link for link in links if link.status == "active"]
        free = [link for link in active if not link.pinned]

        pinned_sum = sum(link.share for link in active if link.pinned)
        if pinned_sum > 100:
            raise ValidationError(
                "Сумма закреплённых долей не может превышать 100%"
            )
        if not free:
            # Все активные закреплены: делить нечего. Сумму ≠ 100% здесь не
            # отклоняем (иначе нельзя закрепить офферы по одному), она
            # блокируется при публикации в _check_total().
            return

        base, extra = divmod(100 - pinned_sum, len(free))
        for i, link in enumerate(free):
            link.share = base + (1 if i < extra else 0)

    async def _stream_view(self, stream: Stream) -> StreamOut:
        links = await self._links.list_by_streams([stream.id])
        offers_by_id = await self._offers_by_id(
            link.offer_id for link in links
        )
        return self._build_stream_view(stream, links, offers_by_id)

    @staticmethod
    def _build_stream_view(
        stream: Stream,
        links: list[StreamOffer],
        offers_by_id: dict[int, Offer],
    ) -> StreamOut:
        offers = []
        for link in links:
            offer = offers_by_id.get(link.offer_id)
            offers.append(
                StreamOfferOut(
                    id=link.id,
                    offer_id=offer.keitaro_id if offer else 0,
                    name=offer.name if offer else "",
                    preview_path=offer.preview_path if offer else "",
                    share=link.share,
                    pinned=link.pinned,
                    status=link.status,
                    is_unpublished=link.is_unpublished,
                    is_deleted_unpublished=link.is_deleted_unpublished,
                )
            )
        return StreamOut(
            id=stream.id,
            keitaro_id=stream.keitaro_id,
            name=stream.name,
            position=stream.position,
            filters=stream.filters,
            clicks_today=stream.clicks_today,
            has_changes=any(
                link.is_unpublished or link.is_deleted_unpublished
                for link in links
            ),
            offers=offers,
        )

    async def _campaign_view(self, campaign: Campaign) -> CampaignOut:
        streams = await self._streams.list_by_campaign(campaign.id)
        links_by_stream = await self._load_links_by_stream(
            [s.id for s in streams]
        )
        offers_by_id = await self._offers_by_id(
            link.offer_id
            for links in links_by_stream.values()
            for link in links
        )
        return CampaignOut(
            id=campaign.id,
            keitaro_id=campaign.keitaro_id,
            name=campaign.name,
            streams=[
                self._build_stream_view(
                    s, links_by_stream.get(s.id, []), offers_by_id
                )
                for s in streams
            ],
        )
