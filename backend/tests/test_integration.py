import asyncio
import os
from collections.abc import AsyncIterator, Iterator
from typing import Any

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.models import Base, Campaign, Offer, Stream, StreamOffer
from app.repositories.base import BaseRepository
from app.repositories.campaign import CampaignRepository
from app.repositories.offer import OfferRepository
from app.services.exceptions import NotFoundError, ValidationError
from app.services.stream_editor import StreamEditor

TEST_DB_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://adrobot:adrobot@localhost:5435/adrobot_test",
)
ADMIN_DB_URL = os.environ.get(
    "TEST_ADMIN_DATABASE_URL",
    "postgresql+asyncpg://adrobot:adrobot@localhost:5435/postgres",
)


async def _admin_sql(sql: str) -> None:
    engine = create_async_engine(ADMIN_DB_URL, isolation_level="AUTOCOMMIT")
    async with engine.connect() as conn:
        await conn.execute(text(sql))
    await engine.dispose()


@pytest.fixture(scope="session")
def test_database() -> Iterator[None]:
    drop = "drop database if exists adrobot_test with (force)"
    asyncio.run(_admin_sql(drop))
    asyncio.run(_admin_sql("create database adrobot_test"))
    yield
    asyncio.run(_admin_sql(drop))


@pytest.fixture
async def db_session(
    test_database: None,
) -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(TEST_DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


def make_campaign(keitaro_id: int = 1) -> Campaign:
    return Campaign(
        keitaro_id=keitaro_id,
        name="test_x_1",
        alias="test-x-1",
        domain_id=10,
        group_id="20",
        traffic_source_id=30,
        status="synced",
    )


async def test_campaign_add_and_get(db_session: AsyncSession) -> None:
    repo = CampaignRepository(db_session)
    added = await repo.add(make_campaign(5))
    await db_session.flush()
    found = await repo.get_by_id(added.id)
    assert found is not None
    assert found.keitaro_id == 5
    assert found.created_at is not None


async def test_campaign_get_by_keitaro_id(
    db_session: AsyncSession,
) -> None:
    repo = CampaignRepository(db_session)
    await repo.add(make_campaign(7))
    await db_session.flush()
    assert (await repo.get_by_keitaro_id(7)) is not None
    assert (await repo.get_by_keitaro_id(8)) is None


async def test_campaign_list(db_session: AsyncSession) -> None:
    repo = CampaignRepository(db_session)
    await repo.add(make_campaign(1))
    await repo.add(make_campaign(2))
    await db_session.flush()
    assert len(await repo.list()) == 2


async def test_campaign_update(db_session: AsyncSession) -> None:
    repo = CampaignRepository(db_session)
    item = await repo.add(make_campaign(1))
    await db_session.flush()
    item.name = "test_x_2"
    await repo.update(item)
    await db_session.flush()
    found = await repo.get_by_id(item.id)
    assert found is not None
    assert found.name == "test_x_2"


async def test_campaign_delete(db_session: AsyncSession) -> None:
    repo = CampaignRepository(db_session)
    item = await repo.add(make_campaign(1))
    await db_session.flush()
    await repo.delete(item)
    await db_session.flush()
    assert (await repo.get_by_id(item.id)) is None


async def test_campaign_keitaro_id_unique(
    db_session: AsyncSession,
) -> None:
    repo = CampaignRepository(db_session)
    await repo.add(make_campaign(1))
    with pytest.raises(IntegrityError):
        await repo.add(make_campaign(1))
        await db_session.flush()


async def test_offer_get_by_keitaro_id(db_session: AsyncSession) -> None:
    repo = OfferRepository(db_session)
    await repo.add(Offer(keitaro_id=18813, name="offer"))
    await db_session.flush()
    found = await repo.get_by_keitaro_id(18813)
    assert found is not None
    assert found.preview_path == ""
    assert (await repo.get_by_keitaro_id(1)) is None


async def test_stream_offer_unique_pair(db_session: AsyncSession) -> None:
    campaigns = BaseRepository(db_session, Campaign)
    streams = BaseRepository(db_session, Stream)
    offers = BaseRepository(db_session, Offer)
    links = BaseRepository(db_session, StreamOffer)
    campaign = await campaigns.add(make_campaign(1))
    offer = await offers.add(Offer(keitaro_id=2, name="o"))
    await db_session.flush()
    stream = await streams.add(
        Stream(
            keitaro_id=3,
            campaign_id=campaign.id,
            name="s",
            type="regular",
            schema="landings",
            action_type="http",
            position=1,
        )
    )
    await db_session.flush()
    await links.add(
        StreamOffer(stream_id=stream.id, offer_id=offer.id, share=100)
    )
    await db_session.flush()
    with pytest.raises(IntegrityError):
        await links.add(
            StreamOffer(stream_id=stream.id, offer_id=offer.id, share=50)
        )
        await db_session.flush()


# ===========================================================================
# ===========================================================================
#  ИНТЕГРАЦИОННЫЕ ТЕСТЫ StreamEditor
#  Настоящие репозитории и настоящий Postgres (db_session),
#  Keitaro подменён на fake_keitaro из conftest.
# ===========================================================================
# ===========================================================================

CAMPAIGN_KT = 500
STREAM_KT = 700


@pytest.fixture
def editor(db_session: AsyncSession, fake_keitaro) -> StreamEditor:
    return StreamEditor(db_session, fake_keitaro)


async def make_stream(db_session: AsyncSession) -> Stream:
    campaign = Campaign(
        keitaro_id=CAMPAIGN_KT,
        name="test_x_c",
        alias="test-x-c",
        domain_id=1,
        group_id="1",
        traffic_source_id=0,
        status="synced",
    )
    db_session.add(campaign)
    await db_session.flush()
    stream = Stream(
        keitaro_id=STREAM_KT,
        campaign_id=campaign.id,
        name="Selected Offer",
        type="default",
        schema="landings",
        action_type="http",
        position=1,
        filters="",
        clicks_today=0,
    )
    db_session.add(stream)
    await db_session.flush()
    return stream


async def make_link(
    db_session: AsyncSession,
    stream: Stream,
    offer_kt: int,
    share: int,
    **fields: Any,
) -> StreamOffer:
    offer = await OfferRepository(db_session).get_by_keitaro_id(offer_kt)
    if offer is None:
        offer = Offer(
            keitaro_id=offer_kt, name=f"offer {offer_kt}", preview_path=""
        )
        db_session.add(offer)
        await db_session.flush()
    params: dict[str, Any] = {
        "share": share,
        "pinned": False,
        "status": "active",
        "is_unpublished": False,
        "is_deleted_unpublished": False,
    }
    params.update(fields)
    link = StreamOffer(stream_id=stream.id, offer_id=offer.id, **params)
    db_session.add(link)
    await db_session.flush()
    return link


def shares(out: Any) -> list[int]:
    return [o.share for o in out.offers]


async def all_links(db_session: AsyncSession) -> list[StreamOffer]:
    rows = await db_session.execute(select(StreamOffer))
    return list(rows.scalars().all())


async def test_editor_view_campaign_not_loaded(editor: StreamEditor) -> None:
    with pytest.raises(NotFoundError):
        await editor.view_campaign(CAMPAIGN_KT)


async def test_editor_add_offer_rebalances_and_marks_unpublished(
    editor: StreamEditor, db_session: AsyncSession, fake_keitaro
) -> None:
    stream = await make_stream(db_session)
    await make_link(db_session, stream, 1, 100)
    fake_keitaro.get_responses["/offers"] = [{"id": 2, "name": "B"}]

    out = await editor.add_offer(stream.id, 2)

    assert shares(out) == [50, 50]
    assert out.offers[1].is_unpublished is True
    assert out.has_changes is True
    assert len(await all_links(db_session)) == 2
    assert (await OfferRepository(db_session).get_by_keitaro_id(2)) is not None


async def test_editor_add_offer_already_active(
    editor: StreamEditor, db_session: AsyncSession
) -> None:
    stream = await make_stream(db_session)
    await make_link(db_session, stream, 1, 100)

    with pytest.raises(ValidationError):
        await editor.add_offer(stream.id, 1)


async def test_editor_remove_published_offer_goes_gray(
    editor: StreamEditor, db_session: AsyncSession
) -> None:
    stream = await make_stream(db_session)
    await make_link(db_session, stream, 1, 50)
    second = await make_link(db_session, stream, 2, 50)

    out = await editor.remove_offer(second.id)

    assert shares(out) == [100, 0]
    assert out.offers[1].status == "removed"
    assert out.has_changes is True
    assert len(await all_links(db_session)) == 2


async def test_editor_remove_unpublished_offer_deletes_row(
    editor: StreamEditor, db_session: AsyncSession
) -> None:
    stream = await make_stream(db_session)
    await make_link(db_session, stream, 1, 50)
    new = await make_link(db_session, stream, 2, 50, is_unpublished=True)
    new_offer_id = new.offer_id

    out = await editor.remove_offer(new.id)

    assert len(out.offers) == 1
    assert shares(out) == [100]
    links = await all_links(db_session)
    assert len(links) == 1
    assert links[0].offer_id != new_offer_id


async def test_editor_remove_already_removed(
    editor: StreamEditor, db_session: AsyncSession
) -> None:
    stream = await make_stream(db_session)
    link = await make_link(db_session, stream, 1, 0, status="removed")

    with pytest.raises(ValidationError):
        await editor.remove_offer(link.id)


async def test_editor_bring_back_restores_published_offer(
    editor: StreamEditor, db_session: AsyncSession
) -> None:
    stream = await make_stream(db_session)
    await make_link(db_session, stream, 1, 50)
    second = await make_link(db_session, stream, 2, 50)
    await editor.remove_offer(second.id)

    out = await editor.bring_back(second.id)

    assert shares(out) == [50, 50]
    assert out.offers[1].status == "active"
    assert out.offers[1].is_unpublished is False
    assert out.has_changes is False


async def test_editor_bring_back_active_offer(
    editor: StreamEditor, db_session: AsyncSession
) -> None:
    stream = await make_stream(db_session)
    link = await make_link(db_session, stream, 1, 100)

    with pytest.raises(ValidationError):
        await editor.bring_back(link.id)


async def test_editor_pin_keeps_share_on_rebalance(
    editor: StreamEditor, db_session: AsyncSession, fake_keitaro
) -> None:
    stream = await make_stream(db_session)
    first = await make_link(db_session, stream, 1, 34)
    await make_link(db_session, stream, 2, 33)
    await make_link(db_session, stream, 3, 33)
    await editor.set_pin(first.id, True)
    fake_keitaro.get_responses["/offers"] = [{"id": 4, "name": "D"}]

    out = await editor.add_offer(stream.id, 4)

    assert shares(out) == [34, 22, 22, 22]
    assert out.offers[0].pinned is True


async def test_editor_pin_removed_offer_rejected(
    editor: StreamEditor, db_session: AsyncSession
) -> None:
    stream = await make_stream(db_session)
    link = await make_link(db_session, stream, 1, 0, status="removed")

    with pytest.raises(ValidationError):
        await editor.set_pin(link.id, True)


async def test_editor_push_sends_active_offers(
    editor: StreamEditor, db_session: AsyncSession, fake_keitaro
) -> None:
    stream = await make_stream(db_session)
    await make_link(db_session, stream, 1, 60)
    await make_link(db_session, stream, 2, 40, is_unpublished=True)
    await make_link(db_session, stream, 3, 0, status="removed")

    out = await editor.push(stream.id)

    assert fake_keitaro.put_calls == [
        (
            f"/streams/{STREAM_KT}",
            {
                "offers": [
                    {"offer_id": 1, "share": 60, "state": "active"},
                    {"offer_id": 2, "share": 40, "state": "active"},
                ]
            },
        )
    ]
    assert out.has_changes is False


async def test_editor_push_rejects_bad_share_sum(
    editor: StreamEditor, db_session: AsyncSession, fake_keitaro
) -> None:
    stream = await make_stream(db_session)
    await make_link(db_session, stream, 1, 60)
    await make_link(db_session, stream, 2, 30)

    with pytest.raises(ValidationError):
        await editor.push(stream.id)

    assert fake_keitaro.put_calls == []


async def test_editor_cancel_returns_keitaro_state(
    editor: StreamEditor, db_session: AsyncSession, fake_keitaro
) -> None:
    stream = await make_stream(db_session)
    await make_link(db_session, stream, 1, 50)
    await make_link(db_session, stream, 2, 50, is_unpublished=True)
    fake_keitaro.get_responses[f"/campaigns/{CAMPAIGN_KT}/streams"] = [
        {"id": STREAM_KT, "offers": [{"offer_id": 1, "share": 100}]}
    ]

    out = await editor.cancel(stream.id)

    assert shares(out) == [100]
    assert out.has_changes is False
    assert len(await all_links(db_session)) == 1


async def test_editor_cancel_stream_missing_in_keitaro(
    editor: StreamEditor, db_session: AsyncSession, fake_keitaro
) -> None:
    stream = await make_stream(db_session)
    fake_keitaro.get_responses[f"/campaigns/{CAMPAIGN_KT}/streams"] = []

    with pytest.raises(NotFoundError):
        await editor.cancel(stream.id)


async def test_editor_fetch_marks_offer_removed_in_keitaro(
    editor: StreamEditor, db_session: AsyncSession, fake_keitaro
) -> None:
    stream = await make_stream(db_session)
    await make_link(db_session, stream, 1, 50)
    await make_link(db_session, stream, 2, 50)
    fake_keitaro.get_responses[f"/campaigns/{CAMPAIGN_KT}/streams"] = [
        {
            "id": STREAM_KT,
            "name": "Selected Offer",
            "type": "default",
            "schema": "landings",
            "action_type": "http",
            "position": 1,
            "filters": [{"name": "country"}],
            "offers": [{"offer_id": 1, "share": 100}],
        }
    ]
    fake_keitaro.post_queues["/report/build"] = [
        {"rows": [{"stream_id": STREAM_KT, "clicks": 5}]}
    ]

    out = await editor.fetch(CAMPAIGN_KT)

    view = out.streams[0]
    assert shares(view) == [100, 0]
    assert view.offers[1].status == "removed"
    assert view.clicks_today == 5
    assert view.filters == "country"
