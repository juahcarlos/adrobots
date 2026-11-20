import logging
import re
from typing import Any

import pycountry
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.keitaro import KeitaroClient, KeitaroError
from app.models import Campaign, Offer, Stream, StreamOffer
from app.repositories.campaign import CampaignRepository
from app.repositories.offer import OfferRepository
from app.repositories.stream import StreamRepository
from app.repositories.stream_offer import StreamOfferRepository
from app.schemas.campaign import CreateCampaignRequest
from app.services.exceptions import (
    CampaignStepError,
    DbError,
    StreamGoogleError,
    StreamOfferError,
    ValidationError,
)

logger = logging.getLogger(__name__)

_PATH = __file__


class CampaignCreator:
    def __init__(
        self,
        session: AsyncSession,
        keitaro: KeitaroClient,
        group_id: str,
    ) -> None:
        self._session = session
        self._keitaro = keitaro
        self._group_id = group_id
        self._campaigns = CampaignRepository(session)
        self._streams = StreamRepository(session)
        self._offers = OfferRepository(session)
        self._stream_offers = StreamOfferRepository(session)

    async def create(self, request: CreateCampaignRequest) -> tuple[int, str]:
        self._validate(request)
        offer_info = await self._get_offer_info(request.offer_id)
        payload = await self._campaign_payload(request)
        db_id, google_pk, offer_pk = await self._save_pending(
            request, payload, offer_info
        )

        campaign_id = None
        stream_google_id = None
        stream_offer_id = None

        try:
            campaign_id = await self._create_campaign(payload)
            await self._mark(Campaign, db_id, keitaro_id=campaign_id)
            stream_google_id = await self._create_stream_google(
                campaign_id, request.geo
            )
            await self._mark(Stream, google_pk, keitaro_id=stream_google_id)
            stream_offer_id = await self._create_stream_offer(
                campaign_id, request.offer_id
            )
            await self._mark(Stream, offer_pk, keitaro_id=stream_offer_id)
            await self._mark(Campaign, db_id, status="synced")
        except Exception as e:
            logger.exception(
                "Ошибка создания кампании: campaign_id=%s, "
                "stream_google_id=%s, stream_offer_id=%s",
                campaign_id,
                stream_google_id,
                stream_offer_id,
            )
            await self._session.rollback()
            cleaned = await self._compensate(
                campaign_id, stream_google_id, stream_offer_id
            )
            await self._mark_failed(
                db_id, google_pk, offer_pk, str(e), cleaned
            )
            raise

        return campaign_id, payload["name"]

    async def _mark(self, model: type, pk: int, **values: Any) -> None:
        obj = await self._session.get(model, pk)
        for key, value in values.items():
            setattr(obj, key, value)
        await self._session.commit()

    async def _mark_failed(
        self,
        db_id: int,
        google_pk: int,
        offer_pk: int,
        error: str,
        cleaned: bool,
    ) -> None:
        """Ставит failed; keitaro_id обнуляет, только если Keitaro очищен.

        Если удаление в Keitaro не удалось, внешние ID остаются в базе
        для ручной чистки.
        """
        try:
            if cleaned:
                await self._mark(Stream, google_pk, keitaro_id=None)
                await self._mark(Stream, offer_pk, keitaro_id=None)
            await self._mark(
                Campaign,
                db_id,
                status="failed",
                last_error=error[:1000],
                **({"keitaro_id": None} if cleaned else {}),
            )
        except Exception as e:
            await self._session.rollback()
            logger.error(
                "\n\n !!! --- ERROR --- !!! %s %s.%s %s db_id=%s e=%s\n\n",
                _PATH,
                "CampaignCreator",
                "_mark_failed",
                "не удалось записать статус failed",
                db_id,
                e,
            )

    async def _compensate(
        self,
        campaign_id: int | None,
        stream_google_id: int | None,
        stream_offer_id: int | None,
    ) -> bool:
        """Удаляет созданное в Keitaro в обратном порядке создания.

        Ошибки удаления только логируются и не подменяют исходную ошибку;
        при сбое одного удаления остальные всё равно выполняются.
        Возвращает True, если всё удалено без ошибок.
        """
        steps: list[tuple[str, str]] = []
        if stream_offer_id is not None:
            steps.append(("поток оффера", f"/streams/{stream_offer_id}"))
        if stream_google_id is not None:
            steps.append(("поток Google", f"/streams/{stream_google_id}"))
        if campaign_id is not None:
            steps.append(("кампания", f"/campaigns/{campaign_id}"))

        ok = True
        for title, path in steps:
            try:
                await self._keitaro.delete(path)
            except Exception as e:
                ok = False
                logger.error(
                    "\n\n !!! --- ERROR --- !!! %s %s.%s "
                    "Ошибка компенсации: не удалось удалить %s (%s) "
                    "campaign_id=%s e=%s\n\n",
                    _PATH,
                    "CampaignCreator",
                    "_compensate",
                    title,
                    path,
                    campaign_id,
                    e,
                )
        return ok

    def _validate(self, request: CreateCampaignRequest) -> None:
        name = request.name.strip()
        if not name:
            raise ValidationError("Название кампании не заполнено")
        geo = request.geo.strip().upper()
        if not geo or pycountry.countries.get(alpha_2=geo) is None:
            raise ValidationError(f"Некорректный код страны: {request.geo}")
        if request.offer_id <= 0:
            raise ValidationError("Оффер не выбран")
        if not self._group_id:
            raise ValidationError("Не настроен GROUP_ID")

    async def _get_offer_info(self, offer_id: int) -> dict:
        try:
            data = await self._keitaro.get_offers()
        except KeitaroError as e:
            logger.error(
                "\n\n !!! --- ERROR --- !!! %s %s.%s %s e=%s\n\n",
                _PATH,
                "CampaignCreator",
                "_get_offer_info",
                "Keitaro не вернул офферы",
                e,
            )
            raise CampaignStepError(str(e)) from e
        for item in data:
            if str(item.get("id")) == str(offer_id):
                return item
        raise ValidationError(f"Оффер с id={offer_id} не найден в Keitaro")

    async def _single_item(self, path: str) -> dict:
        try:
            data = await self._keitaro.get(path)
        except KeitaroError as e:
            logger.error(
                "\n\n !!! --- ERROR --- !!! %s %s.%s %s e=%s\n\n",
                _PATH,
                "CampaignCreator",
                "_single_item",
                "Keitaro не вернул справочник",
                e,
            )
            raise CampaignStepError(str(e)) from e
        items = data if isinstance(data, list) else [data]
        if len(items) != 1:
            raise CampaignStepError(
                f"Ожидался ровно один элемент в {path}, получено: {len(items)}"
            )
        return items[0]

    async def _campaign_payload(self, request: CreateCampaignRequest) -> dict:
        domain = await self._single_item("/domains")
        traffic_source = await self._optional_item("/traffic_sources")
        return {
            "name": request.name.strip(),
            "alias": request.name.strip().replace("_", "-"),
            "domain_id": int(domain["id"]),
            "group_id": str(self._group_id),
            "traffic_source_id": (
                int(traffic_source["id"]) if traffic_source else 0
            ),
        }

    async def _create_campaign(self, payload: dict) -> int:
        try:
            data = await self._keitaro.post("/campaigns", payload)
        except KeitaroError as e:
            logger.error(
                "\n\n !!! --- ERROR --- !!! %s %s.%s %s e=%s\n\n",
                _PATH,
                "CampaignCreator",
                "_create_campaign",
                "не удалось создать кампанию",
                e,
            )
            raise CampaignStepError(str(e)) from e
        try:
            return int(data["id"])
        except (KeyError, TypeError, ValueError) as e:
            logger.error(
                "\n\n !!! --- ERROR --- !!! %s %s.%s %s e=%s\n\n",
                _PATH,
                "CampaignCreator",
                "_create_campaign",
                "некорректный ответ Keitaro",
                e,
            )
            raise CampaignStepError(
                f"Некорректный ответ Keitaro: {data}"
            ) from e

    async def _optional_item(self, path: str) -> dict | None:
        try:
            data = await self._keitaro.get(path)
        except KeitaroError as e:
            logger.error(
                "\n\n !!! --- ERROR --- !!! %s %s.%s %s e=%s\n\n",
                _PATH,
                "CampaignCreator",
                "_optional_item",
                "Keitaro не вернул справочник",
                e,
            )
            raise CampaignStepError(str(e)) from e
        items = data if isinstance(data, list) else [data]
        return items[0] if items else None

    def _stream_google_payload(
        self, campaign_id: int, geo: str
    ) -> dict[str, Any]:
        return {
            "campaign_id": campaign_id,
            "name": "Google GEO",
            "position": 1,
            "type": "forced",
            "schema": "redirect",
            "filters": [
                {
                    "name": "country",
                    "mode": "accept",
                    "payload": [geo.strip().upper()],
                }
            ],
            "action_type": "http",
            "action_options": {"url": "https://www.google.com"},
            "state": "active",
            "collect_clicks": True,
        }

    def _stream_offer_payload(
        self, campaign_id: int, offer_id: int
    ) -> dict[str, Any]:
        return {
            "campaign_id": campaign_id,
            "name": "Selected Offer",
            "position": 2,
            "type": "default",
            "schema": "landings",
            "offers": [
                {"offer_id": offer_id, "share": 100, "state": "active"}
            ],
            "action_type": "http",
            "state": "active",
            "collect_clicks": True,
        }

    async def _create_stream_google(self, campaign_id: int, geo: str) -> int:
        payload = self._stream_google_payload(campaign_id, geo)
        try:
            data = await self._keitaro.post("/streams", payload)
        except KeitaroError as e:
            logger.error(
                "\n\n !!! --- ERROR --- !!! %s %s.%s %s e=%s\n\n",
                _PATH,
                "CampaignCreator",
                "_create_stream_google",
                "не удалось создать поток Google",
                e,
            )
            raise StreamGoogleError(str(e), campaign_id) from e
        try:
            return int(data["id"])
        except (KeyError, TypeError, ValueError) as e:
            logger.error(
                "\n\n !!! --- ERROR --- !!! %s %s.%s %s e=%s\n\n",
                _PATH,
                "CampaignCreator",
                "_create_stream_google",
                "некорректный ответ Keitaro",
                e,
            )
            raise StreamGoogleError(
                f"Некорректный ответ Keitaro: {data}", campaign_id
            ) from e

    async def _create_stream_offer(
        self, campaign_id: int, offer_id: int
    ) -> int:
        payload = self._stream_offer_payload(campaign_id, offer_id)
        try:
            data = await self._keitaro.post("/streams", payload)
        except KeitaroError as e:
            logger.error(
                "\n\n !!! --- ERROR --- !!! %s %s.%s %s e=%s\n\n",
                _PATH,
                "CampaignCreator",
                "_create_stream_offer",
                "не удалось создать поток оффера",
                e,
            )
            raise StreamOfferError(str(e), campaign_id) from e
        try:
            return int(data["id"])
        except (KeyError, TypeError, ValueError) as e:
            logger.error(
                "\n\n !!! --- ERROR --- !!! %s %s.%s %s e=%s\n\n",
                _PATH,
                "CampaignCreator",
                "_create_stream_offer",
                "некорректный ответ Keitaro",
                e,
            )
            raise StreamOfferError(
                f"Некорректный ответ Keitaro: {data}", campaign_id
            ) from e

    async def _save_pending(
        self,
        request: CreateCampaignRequest,
        campaign_payload: dict,
        offer_info: dict,
    ) -> tuple[int, int, int]:
        """Пишет кампанию и потоки со статусом pending одной транзакцией.

        Возвращает локальные id: кампания, поток Google, поток оффера.
        """
        try:
            campaign = await self._campaigns.add(
                Campaign(
                    name=campaign_payload["name"],
                    alias=campaign_payload["alias"],
                    domain_id=campaign_payload["domain_id"],
                    group_id=campaign_payload["group_id"],
                    traffic_source_id=campaign_payload["traffic_source_id"],
                    geo=request.geo.strip().upper(),
                    status="pending",
                )
            )
            stream_google = await self._streams.add(
                Stream(
                    campaign_id=campaign.id,
                    name="Google GEO",
                    type="forced",
                    schema="redirect",
                    action_type="http",
                    position=1,
                )
            )
            stream_offer = await self._streams.add(
                Stream(
                    campaign_id=campaign.id,
                    name="Selected Offer",
                    type="default",
                    schema="landings",
                    action_type="http",
                    position=2,
                )
            )
            offer = await self._offers.get_by_keitaro_id(request.offer_id)
            if offer is None:
                offer = await self._offers.add(
                    Offer(
                        keitaro_id=request.offer_id,
                        name=str(offer_info.get("name") or ""),
                        preview_path=str(offer_info.get("preview_path") or ""),
                    )
                )
            await self._stream_offers.add(
                StreamOffer(
                    stream_id=stream_offer.id,
                    offer_id=offer.id,
                    share=100,
                    pinned=False,
                    status="active",
                    is_unpublished=False,
                    is_deleted_unpublished=False,
                )
            )
            ids = (campaign.id, stream_google.id, stream_offer.id)
            await self._session.commit()
            return ids
        except Exception as e:
            await self._session.rollback()
            logger.error(
                "\n\n !!! --- ERROR --- !!! %s %s.%s %s e=%s\n\n",
                _PATH,
                "CampaignCreator",
                "_save_pending",
                "не удалось сохранить в БД",
                e,
            )
            raise DbError(str(e), None) from e
