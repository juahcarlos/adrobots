import pytest
from httpx import AsyncClient

from app.schemas.campaign import CreateCampaignRequest
from app.services.campaign_creator import CampaignCreator
from app.services.exceptions import (
    CampaignStepError,
    DbError,
    StreamGoogleError,
    StreamOfferError,
)
from tests.conftest import (
    FakeKeitaro,
    FakeRepo,
    KeitaroError,
    override_dependencies,
)


@pytest.fixture
def app_client(client: AsyncClient) -> AsyncClient:
    return client


async def test_health(app_client: AsyncClient):
    resp = await app_client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


async def test_countries(app_client: AsyncClient):
    resp = await app_client.get("/countries")
    assert resp.status_code == 200
    codes = resp.json()
    assert isinstance(codes, list)
    assert "DE" in codes and "US" in codes and "RU" in codes


async def test_offers_ok(app_client: AsyncClient):
    fake = FakeKeitaro()
    fake.get_responses = {
        "/offers": [{"id": 1, "name": "A"}, {"id": 2, "name": "B"}]
    }
    app_client._transport.app.state.keitaro = fake
    override_dependencies(app_client, keitaro=fake)
    resp = await app_client.get("/offers")
    assert resp.status_code == 200
    assert resp.json() == [{"id": 1, "name": "A"}, {"id": 2, "name": "B"}]


async def test_offers_error(app_client: AsyncClient):
    fake = FakeKeitaro()
    fake.get_responses = {"/offers": KeitaroError("no auth")}
    app_client._transport.app.state.keitaro = fake
    override_dependencies(app_client, keitaro=fake)
    resp = await app_client.get("/offers")
    assert resp.status_code == 502
    body = resp.json()
    assert body["source"] == "offers"
    assert body["error"] == "no auth"


def patch_creator(app_client: AsyncClient, creator: object) -> None:
    override_dependencies(app_client, campaign_creator=creator)


def make_creator(fake: FakeKeitaro, session) -> CampaignCreator:
    creator = CampaignCreator.__new__(CampaignCreator)
    creator._session = session
    creator._keitaro = fake
    creator._group_id = "10332"
    creator._campaigns = FakeRepo()
    creator._streams = FakeRepo()
    creator._offers = FakeRepo()
    creator._stream_offers = FakeRepo()
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


async def test_post_campaigns_ok(app_client: AsyncClient, session):
    fake = FakeKeitaro()
    fill_keitaro(fake)
    patch_creator(app_client, make_creator(fake, session))
    resp = await app_client.post(
        "/campaigns",
        json={"name": "test_ivanov_c1", "geo": "DE", "offer_id": 42},
    )
    assert resp.status_code == 200
    assert resp.json() == {"campaign_id": 100, "name": "test_ivanov_c1"}


@pytest.mark.parametrize(
    "payload,status,step,campaign_id",
    [
        (
            {"name": "bad", "geo": "DE", "offer_id": 42},
            422,
            "validation",
            None,
        ),
        (
            {"name": "test_ivanov_c1", "geo": "XX", "offer_id": 42},
            422,
            "validation",
            None,
        ),
        (
            {"name": "test_ivanov_c1", "geo": "", "offer_id": 42},
            422,
            "validation",
            None,
        ),
        (
            {"name": "test_ivanov_c1", "geo": "deu", "offer_id": 42},
            422,
            "validation",
            None,
        ),
        (
            {"name": "", "geo": "DE", "offer_id": 42},
            422,
            "validation",
            None,
        ),
        (
            {"name": "test_ivanov_c1", "geo": "DE", "offer_id": "x"},
            422,
            "validation",
            None,
        ),
    ],
)
async def test_post_campaigns_validation(
    app_client: AsyncClient,
    session,
    payload,
    status,
    step,
    campaign_id,
):
    fake = FakeKeitaro()
    patch_creator(app_client, make_creator(fake, session))
    resp = await app_client.post("/campaigns", json=payload)
    assert resp.status_code == status
    body = resp.json()
    assert body["step"] == step
    assert body["campaign_id"] == campaign_id
    assert body["error"]


@pytest.mark.parametrize(
    "exc,status,step",
    [
        (CampaignStepError("k err"), 502, "campaign"),
        (StreamGoogleError("s1", 100), 502, "stream_google"),
        (StreamOfferError("s2", 100), 502, "stream_offer"),
        (DbError("db", 100), 500, "db"),
    ],
)
async def test_post_campaigns_steps(
    app_client: AsyncClient,
    exc,
    status,
    step,
):
    class FailingCreator:
        async def create(self, request: CreateCampaignRequest):
            raise exc

    override_dependencies(app_client, campaign_creator=FailingCreator())
    resp = await app_client.post(
        "/campaigns",
        json={"name": "test_ivanov_c1", "geo": "DE", "offer_id": 42},
    )
    assert resp.status_code == status
    body = resp.json()
    assert body["step"] == step
    assert body["error"] == exc.error
    assert body["campaign_id"] == exc.campaign_id


async def test_post_campaigns_validation_no_keitaro_calls(
    app_client: AsyncClient, session
):
    fake = FakeKeitaro()
    patch_creator(app_client, make_creator(fake, session))
    await app_client.post(
        "/campaigns",
        json={"name": "nope", "geo": "DE", "offer_id": 42},
    )
    assert fake.get_calls == []
    assert fake.post_calls == []
