from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Campaign(Base):
    __tablename__ = "campaigns"

    id: Mapped[int | None] = mapped_column(
        Integer, primary_key=True, nullable=True
    )
    keitaro_id: Mapped[int | None] = mapped_column(
        Integer, unique=True, nullable=True
    )
    name: Mapped[str] = mapped_column(String(255))
    alias: Mapped[str] = mapped_column(String(255))
    domain_id: Mapped[int] = mapped_column(Integer)
    group_id: Mapped[str] = mapped_column(String(64))
    traffic_source_id: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    last_error: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    geo: Mapped[str | None] = mapped_column(String(8), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    streams: Mapped[list["Stream"]] = relationship(back_populates="campaign")


class Stream(Base):
    __tablename__ = "streams"

    id: Mapped[int | None] = mapped_column(
        Integer, primary_key=True, nullable=True
    )
    keitaro_id: Mapped[int | None] = mapped_column(
        Integer, unique=True, nullable=True
    )
    campaign_id: Mapped[int] = mapped_column(
        ForeignKey("campaigns.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255))
    type: Mapped[str] = mapped_column(String(32))
    schema: Mapped[str] = mapped_column(String(32))
    action_type: Mapped[str] = mapped_column(String(32))
    position: Mapped[int] = mapped_column(Integer)
    filters: Mapped[str] = mapped_column(String(255), default="")
    clicks_today: Mapped[int] = mapped_column(Integer, default=0)

    campaign: Mapped[Campaign] = relationship(back_populates="streams")
    stream_offers: Mapped[list["StreamOffer"]] = relationship(
        back_populates="stream"
    )


class Offer(Base):
    __tablename__ = "offers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    keitaro_id: Mapped[int] = mapped_column(Integer, unique=True)
    name: Mapped[str] = mapped_column(String(255))
    preview_path: Mapped[str] = mapped_column(String(512), default="")

    stream_offers: Mapped[list["StreamOffer"]] = relationship(
        back_populates="offer"
    )


class StreamOffer(Base):
    __tablename__ = "stream_offers"
    __table_args__ = (
        UniqueConstraint("stream_id", "offer_id", name="uq_stream_offer"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    stream_id: Mapped[int] = mapped_column(
        ForeignKey("streams.id"), nullable=False
    )
    offer_id: Mapped[int] = mapped_column(
        ForeignKey("offers.id"), nullable=False
    )
    share: Mapped[int] = mapped_column(Integer)
    pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(16), default="active")
    is_unpublished: Mapped[bool] = mapped_column(Boolean, default=False)
    is_deleted_unpublished: Mapped[bool] = mapped_column(
        Boolean, default=False
    )

    stream: Mapped[Stream] = relationship(back_populates="stream_offers")
    offer: Mapped[Offer] = relationship(back_populates="stream_offers")
