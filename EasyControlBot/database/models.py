from datetime import date
from sqlalchemy import Integer, String, BigInteger, Date, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

class Base(DeclarativeBase):
    pass

class ItemModel(Base):
    __tablename__ = "items"

    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_user_item_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    expires_at: Mapped[date] = mapped_column(Date, nullable=False)
    notified_14_days: Mapped[int] = mapped_column(Integer, default=0)