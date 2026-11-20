import pytest

from app.models import Campaign, Stream
from app.schemas.campaign import CreateCampaignRequest
from app.services.campaign_creator import CampaignCreator
from app.services.exceptions import (
    CampaignStepError,
    DbError,
    StreamGoogleError,
    StreamOfferError,
    ValidationError,
)
from tests.conftest import FakeKeitaro, FakeRepo, KeitaroError

GROUP_ID = "10332"


def make_creator(
    fake_keitaro: FakeKeitaro,
    session,
    offer_repo: FakeRepo | None = None,
) -> CampaignCreator:
    creator = CampaignCreator.__new__(CampaignCreator)
    creator._session = session
    creator._keitaro = fake_keitaro
    creator._group_id = GROUP_ID
    creator._campaigns = FakeRepo()
    creator._streams = FakeRepo()
    creator._offers = offer_repo or FakeRepo()
    creator._stream_offers = FakeRepo()

    async def get(model, pk):
        repo = {Campaign: creator._campaigns, Stream: creator._streams}
        return repo[model].added[pk - 1]

    session.get = get
    return creator


def fill_keitaro(fake: FakeKeitaro) -> None:
    fake.get_responses = {
        "/domains": [{"id": 7}],
        "/traffic_sources": [{"id": 3}],
        "/offers": [
            {"id": 42, "name": "Offer A", "preview_path": "/p/42.png"}
        ],
    }
    fake.post_queues = {
        "/campaigns": [{"id": 100}],
        "/streams": [{"id": 200}, {"id": 201}],
    }


def fail_commit_on(session, n: int) -> None:
    calls = {"n": 0}

    async def commit() -> None:
        calls["n"] += 1
        if calls["n"] == n:
            raise RuntimeError("db down")

    session.commit = commit


def req(**kwargs) -> CreateCampaignRequest:
    base = {"name": "test_ivanov_campaign1", "geo": "DE", "offer_id": 42}
    base.update(kwargs)
    return CreateCampaignRequest.model_construct(**base)


# --- валидация ---


@pytest.mark.parametrize(
    "name",
    ["ivanov_campaign1", "test_campaign1", "test_", "", "test__x"],
)
async def test_invalid_name_rejected(name, fake_keitaro, session):
    creator = make_creator(fake_keitaro, session)
    with pytest.raises(ValidationError):
        await creator.create(req(name=name))
    assert fake_keitaro.get_calls == []
    assert fake_keitaro.post_calls == []


@pytest.mark.parametrize("geo", ["", "XX", "deu"])
async def test_invalid_geo_rejected(geo, fake_keitaro, session):
    creator = make_creator(fake_keitaro, session)
    with pytest.raises(ValidationError):
        await creator.create(req(geo=geo))
    assert fake_keitaro.get_calls == []


async def test_invalid_offer_rejected(fake_keitaro, session):
    creator = make_creator(fake_keitaro, session)
    with pytest.raises(ValidationError):
        await creator.create(req(offer_id=0))
    assert fake_keitaro.get_calls == []


# --- подготовка данных ---


async def test_alias_and_types(fake_keitaro, session):
    fill_keitaro(fake_keitaro)
    creator = make_creator(fake_keitaro, session)
    await creator.create(req(name="test_semyonoff_campain875"))
    _, payload = fake_keitaro.post_calls[0]
    assert payload["alias"] == "test-semyonoff-campain875"
    assert payload["group_id"] == "10332"
    assert isinstance(payload["group_id"], str)
    assert payload["domain_id"] == 7
    assert isinstance(payload["domain_id"], int)
    assert payload["traffic_source_id"] == 3
    assert isinstance(payload["traffic_source_id"], int)


@pytest.mark.parametrize("path", ["/domains"])
async def test_single_item_required(path, fake_keitaro, session):
    fill_keitaro(fake_keitaro)
    fake_keitaro.get_responses[path] = [{"id": 1}, {"id": 2}]
    creator = make_creator(fake_keitaro, session)
    with pytest.raises(CampaignStepError) as exc:
        await creator.create(req())
    assert exc.value.step == "campaign"
    assert exc.value.campaign_id is None
    assert fake_keitaro.post_calls == []


# --- потоки ---


async def test_stream_payloads(fake_keitaro, session):
    fill_keitaro(fake_keitaro)
    creator = make_creator(fake_keitaro, session)
    campaign_id, name = await creator.create(req())
    assert campaign_id == 100
    assert name == "test_ivanov_campaign1"
    s1 = fake_keitaro.post_calls[1][1]
    assert s1["campaign_id"] == 100
    assert s1["schema"] == "redirect"
    assert s1["type"] == "forced"
    assert s1["filters"] == [
        {"name": "country", "mode": "accept", "payload": ["DE"]}
    ]
    assert s1["action_options"] == {"url": "https://www.google.com"}
    s2 = fake_keitaro.post_calls[2][1]
    assert s2["campaign_id"] == 100
    assert s2["schema"] == "landings"
    assert s2["offers"] == [{"offer_id": 42, "share": 100, "state": "active"}]


# --- ошибки по шагам ---


async def test_campaign_error_no_streams(fake_keitaro, session):
    fill_keitaro(fake_keitaro)
    fake_keitaro.post_queues["/campaigns"] = [KeitaroError("boom")]
    creator = make_creator(fake_keitaro, session)
    with pytest.raises(CampaignStepError) as exc:
        await creator.create(req())
    assert exc.value.step == "campaign"
    assert exc.value.error == "boom"
    assert exc.value.campaign_id is None
    assert len(fake_keitaro.post_calls) == 1


async def test_stream_google_error(fake_keitaro, session):
    fill_keitaro(fake_keitaro)
    fake_keitaro.post_queues["/streams"] = [
        KeitaroError("s1 fail"),
        {"id": 201},
    ]
    creator = make_creator(fake_keitaro, session)
    with pytest.raises(StreamGoogleError) as exc:
        await creator.create(req())
    assert exc.value.step == "stream_google"
    assert exc.value.campaign_id == 100
    assert len(fake_keitaro.post_calls) == 2


async def test_stream_offer_error(fake_keitaro, session):
    fill_keitaro(fake_keitaro)
    fake_keitaro.post_queues["/streams"] = [
        {"id": 200},
        KeitaroError("s2 fail"),
    ]
    creator = make_creator(fake_keitaro, session)
    with pytest.raises(StreamOfferError) as exc:
        await creator.create(req())
    assert exc.value.step == "stream_offer"
    assert exc.value.campaign_id == 100


# --- сохранение в БД ---


async def test_db_saved(fake_keitaro, session):
    fill_keitaro(fake_keitaro)
    creator = make_creator(fake_keitaro, session)
    await creator.create(req())
    assert len(creator._campaigns.added) == 1
    assert len(creator._streams.added) == 2
    assert len(creator._offers.added) == 1
    assert len(creator._stream_offers.added) == 1
    so = creator._stream_offers.added[0]
    assert so.share == 100
    assert so.pinned is False
    assert so.status == "active"
    assert so.is_unpublished is False
    assert so.is_deleted_unpublished is False
    assert session.commit.await_count == 5
    campaign = creator._campaigns.added[0]
    assert campaign.status == "synced"
    assert campaign.keitaro_id == 100
    assert campaign.geo == "DE"
    assert [s.keitaro_id for s in creator._streams.added] == [200, 201]


async def test_db_existing_offer_reused(fake_keitaro, session):
    from app.models import Offer

    fill_keitaro(fake_keitaro)
    existing = Offer(keitaro_id=42, name="Offer A", preview_path="/p")
    creator = make_creator(
        fake_keitaro, session, offer_repo=FakeRepo(existing=existing)
    )
    await creator.create(req())
    assert creator._offers.added == []


async def test_db_error(fake_keitaro, session):
    fill_keitaro(fake_keitaro)
    session.commit.side_effect = RuntimeError("db down")
    creator = make_creator(fake_keitaro, session)
    with pytest.raises(DbError) as exc:
        await creator.create(req())
    assert exc.value.step == "db"
    assert fake_keitaro.post_calls == []
    session.rollback.assert_awaited_once()


# --- компенсация при ошибках создания ---


async def test_success_does_not_delete(fake_keitaro, session):
    fill_keitaro(fake_keitaro)
    creator = make_creator(fake_keitaro, session)
    await creator.create(req())
    assert fake_keitaro.delete_calls == []


async def test_stream_google_error_deletes_campaign(fake_keitaro, session):
    fill_keitaro(fake_keitaro)
    fake_keitaro.post_queues["/streams"] = [KeitaroError("s1 fail")]
    creator = make_creator(fake_keitaro, session)
    with pytest.raises(StreamGoogleError) as exc:
        await creator.create(req())
    assert exc.value.campaign_id == 100
    assert fake_keitaro.delete_calls == ["/campaigns/100"]


async def test_stream_offer_error_deletes_first_stream_and_campaign(
    fake_keitaro, session
):
    fill_keitaro(fake_keitaro)
    fake_keitaro.post_queues["/streams"] = [
        {"id": 200},
        KeitaroError("s2 fail"),
    ]
    creator = make_creator(fake_keitaro, session)
    with pytest.raises(StreamOfferError) as exc:
        await creator.create(req())
    assert exc.value.campaign_id == 100
    assert fake_keitaro.delete_calls == ["/streams/200", "/campaigns/100"]


async def test_db_error_deletes_both_streams_and_campaign(
    fake_keitaro, session
):
    fill_keitaro(fake_keitaro)
    fail_commit_on(session, 4)
    creator = make_creator(fake_keitaro, session)
    with pytest.raises(RuntimeError, match="db down"):
        await creator.create(req())
    assert fake_keitaro.delete_calls == [
        "/streams/201",
        "/streams/200",
        "/campaigns/100",
    ]
    campaign = creator._campaigns.added[0]
    assert campaign.status == "failed"
    assert campaign.keitaro_id is None
    assert "db down" in campaign.last_error


async def test_campaign_error_deletes_nothing(fake_keitaro, session):
    fill_keitaro(fake_keitaro)
    fake_keitaro.post_queues["/campaigns"] = [KeitaroError("boom")]
    creator = make_creator(fake_keitaro, session)
    with pytest.raises(CampaignStepError):
        await creator.create(req())
    assert fake_keitaro.delete_calls == []


async def test_compensation_error_keeps_original_error(
    fake_keitaro, session, caplog
):
    fill_keitaro(fake_keitaro)
    fake_keitaro.post_queues["/streams"] = [
        {"id": 200},
        KeitaroError("s2 fail"),
    ]
    fake_keitaro.delete_errors["/streams/200"] = KeitaroError("delete denied")
    creator = make_creator(fake_keitaro, session)
    with caplog.at_level("ERROR"), pytest.raises(StreamOfferError) as exc:
        await creator.create(req())
    # исходная ошибка и campaign_id не подменены ошибкой компенсации
    assert exc.value.error == "s2 fail"
    assert exc.value.campaign_id == 100
    # сбой удаления потока не мешает удалить кампанию
    assert fake_keitaro.delete_calls == ["/streams/200", "/campaigns/100"]
    # ошибка компенсации залогирована отдельно
    messages = [r.getMessage() for r in caplog.records]
    assert any(
        "Ошибка компенсации" in m and "delete denied" in m for m in messages
    )


async def test_compensation_total_failure_keeps_db_error(
    fake_keitaro, session
):
    fill_keitaro(fake_keitaro)
    fail_commit_on(session, 4)
    for path in ("/streams/201", "/streams/200", "/campaigns/100"):
        fake_keitaro.delete_errors[path] = RuntimeError("keitaro down")
    creator = make_creator(fake_keitaro, session)
    with pytest.raises(RuntimeError, match="db down"):
        await creator.create(req())
    assert len(fake_keitaro.delete_calls) == 3
    campaign = creator._campaigns.added[0]
    assert campaign.status == "failed"
    assert campaign.keitaro_id == 100


# --- оригинальный текст ошибки Keitaro доходит до исключения шага ---


async def test_keitaro_error_text_passed_through(fake_keitaro, session):
    fill_keitaro(fake_keitaro)
    original = '{"error":"Alias already exists","code":409}'
    fake_keitaro.post_queues["/campaigns"] = [KeitaroError(original)]
    creator = make_creator(fake_keitaro, session)
    with pytest.raises(CampaignStepError) as exc:
        await creator.create(req())
    assert exc.value.error == original


async def test_keitaro_error_marks_failed(fake_keitaro, session):
    fill_keitaro(fake_keitaro)
    fake_keitaro.post_queues["/streams"] = [
        {"id": 200},
        KeitaroError("s2 fail"),
    ]
    creator = make_creator(fake_keitaro, session)
    with pytest.raises(StreamOfferError):
        await creator.create(req())
    campaign = creator._campaigns.added[0]
    assert campaign.status == "failed"
    assert campaign.keitaro_id is None
    assert all(s.keitaro_id is None for s in creator._streams.added)
    assert "s2 fail" in campaign.last_error


async def test_failed_cleanup_keeps_keitaro_ids(fake_keitaro, session):
    fill_keitaro(fake_keitaro)
    fake_keitaro.post_queues["/streams"] = [
        {"id": 200},
        KeitaroError("s2 fail"),
    ]
    fake_keitaro.delete_errors["/campaigns/100"] = KeitaroError("denied")
    creator = make_creator(fake_keitaro, session)
    with pytest.raises(StreamOfferError):
        await creator.create(req())
    campaign = creator._campaigns.added[0]
    assert campaign.status == "failed"
    assert campaign.keitaro_id == 100
