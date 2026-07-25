from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKeyConstraint, Index, UniqueConstraint, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class TrackerUser(Base):
    __tablename__ = "tracker_users"

    username: Mapped[str] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))

    __table_args__ = (Index("idx_tracker_users_created", "created_at", postgresql_using="btree"),)


class UserBet(Base):
    __tablename__ = "user_bets"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    username: Mapped[str]
    form_id: Mapped[int]
    race_date: Mapped[date]
    bet_type: Mapped[str]
    odds_taken: Mapped[Decimal]
    stake_aud: Mapped[Decimal]
    result_position: Mapped[int | None] = mapped_column(default=None)
    payout_aud: Mapped[Decimal | None] = mapped_column(default=None)
    profit_aud: Mapped[Decimal | None] = mapped_column(default=None)
    settled_at: Mapped[datetime | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(server_default=text("now()"))

    __table_args__ = (
        ForeignKeyConstraint(
            ["form_id", "race_date"],
            ["race_entries.form_id", "race_entries.race_date"],
            name="user_bets_runner_fkey",
            ondelete="RESTRICT",
        ),
        CheckConstraint("bet_type IN ('win', 'place', 'each_way')", name="user_bets_bet_type_check"),
        UniqueConstraint("username", "form_id", "race_date", "bet_type", name="user_bets_dedup"),
        Index("idx_user_bets_username", "username"),
        Index("idx_user_bets_runner", "form_id", "race_date"),
        Index("idx_user_bets_date", "race_date", postgresql_using="btree"),
        Index(
            "idx_user_bets_unsettled",
            "race_date",
            "form_id",
            postgresql_where=text("settled_at IS NULL"),
        ),
    )
