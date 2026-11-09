from datetime import date, datetime

from sqlalchemy import BigInteger, Boolean, Date, DateTime, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.sql import expression


class Base(DeclarativeBase):
    pass


class ItemModel(Base):
    __tablename__ = "items"

    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_user_item_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    expires_at: Mapped[date] = mapped_column(Date, nullable=False)

    # Последняя отправленная стадия напоминания:
    # 0 - ничего не отправлено, 1 - за 14 дней, 2 - за 7 дней, 3 - в день истечения
    notify_stage: Mapped[int] = mapped_column(Integer, default=0, server_default="0")


class BotUser(Base):
    """Все, кто хоть раз написал боту. Нужна для блокировки и списка пользователей."""
    __tablename__ = "bot_users"

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    username: Mapped[str | None] = mapped_column(String(64))
    first_name: Mapped[str | None] = mapped_column(String(255))
    is_banned: Mapped[bool] = mapped_column(Boolean, default=False, server_default=expression.false())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())