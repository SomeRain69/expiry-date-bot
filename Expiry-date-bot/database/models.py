from datetime import date

from sqlalchemy import BigInteger, Date, Integer, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


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
    # 0 - ничего не отправлено, 1 - за 14 дней, 2 - за 7 дней, 3 - в день истечения (или позже)
    notify_stage: Mapped[int] = mapped_column(Integer, default=0, server_default="0")