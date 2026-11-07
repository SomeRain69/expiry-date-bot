from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from config import config
from database.models import Base

engine = create_async_engine(
    config.database_url,
    echo=False,
    pool_pre_ping=True,  # переподключение, если сервер закрыл простаивающее соединение
)
async_session_maker = async_sessionmaker(engine, expire_on_commit=False)


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)