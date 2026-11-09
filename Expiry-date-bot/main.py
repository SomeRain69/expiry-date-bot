import asyncio
import html
import logging
import os
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher
from aiogram.exceptions import TelegramForbiddenError
from aiohttp import web
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

from config import config, TZ
from database.database import init_db, async_session_maker
from database.models import ItemModel
from handlers import start, items, clear

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Стадии напоминаний (в БД в notify_stage хранятся значения 0-3;
# STAGE_EXPIRED в БД не сохраняется, потому что просроченный товар удаляется)
STAGE_NONE = 0     # до срока больше 14 дней, напоминать рано
STAGE_14 = 1       # осталось 14 дней или меньше
STAGE_7 = 2        # осталось 7 дней или меньше
STAGE_DAY = 3      # срок истекает сегодня
STAGE_EXPIRED = 4  # срок уже вышел


# --- ВЕБ-СЕРВЕР ДЛЯ RENDER ---
async def handle(request):
    return web.Response(text="Bot is running!")


async def web_server():
    app = web.Application()
    app.router.add_get("/", handle)
    runner = web.AppRunner(app)
    await runner.setup()

    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()


# --- ЛОГИКА НАПОМИНАНИЙ ---
def stage_for(delta: int) -> int:
    """Какая стадия напоминания соответствует количеству дней до срока."""
    if delta < 0:
        return STAGE_EXPIRED
    if delta == 0:
        return STAGE_DAY
    if delta <= 7:
        return STAGE_7
    if delta <= 14:
        return STAGE_14
    return STAGE_NONE


def build_message(name: str, date_str: str, delta: int, stage: int) -> str | None:
    """Формирует текст сообщения на основе стадии."""
    if stage == STAGE_EXPIRED:
        return f"❌ <b>Просрочка удалена!</b> У товара <b>«{html.escape(name)}»</b> истек срок ({date_str}). Он автоматически удален из системы."

    if stage == STAGE_DAY:
        return f"🚨 <b>Внимание!</b> У товара <b>«{html.escape(name)}»</b> срок годности истекает <b>сегодня</b> ({date_str})!"

    if stage == STAGE_7:
        return f"⏰ <b>Скоро срок!</b> У товара <b>«{html.escape(name)}»</b> осталось {delta} дн. (годен до {date_str})."

    if stage == STAGE_14:
        return f"⚠️ <b>Напоминание!</b> У товара <b>«{html.escape(name)}»</b> осталось {delta} дн. (годен до {date_str})."

    return None


# --- ФОНОВАЯ ПРОВЕРКА СРОКОВ ГОДНОСТИ ---
async def check_expiring_items(bot: Bot):
    today = datetime.now(TZ).date()

    async with async_session_maker() as session:
        # Берём только товары, до срока которых 14 дней или меньше (включая просроченные)
        result = await session.execute(
            select(ItemModel).where(ItemModel.expires_at <= today + timedelta(days=14))
        )
        candidates = result.scalars().all()

        for item in candidates:
            delta = (item.expires_at - today).days
            stage = stage_for(delta)

            if stage == STAGE_NONE:
                continue

            # Просроченные обрабатываем всегда, остальные стадии не повторяем
            if stage != STAGE_EXPIRED and stage <= item.notify_stage:
                continue

            # name передаём как есть: html.escape делается внутри build_message
            msg = build_message(item.name, item.expires_at.strftime("%d.%m.%Y"), delta, stage)
            if msg is None:
                continue

            try:
                await bot.send_message(item.user_id, msg, parse_mode="HTML")
            except TelegramForbiddenError:
                # Пользователь заблокировал бота: повторять отправку бессмысленно
                logger.warning("User %s blocked the bot, skipping notification", item.user_id)
            except Exception:
                logger.exception("Failed to notify user %s about item %s", item.user_id, item.id)
                continue  # ничего не меняем, попробуем при следующей проверке

            if stage == STAGE_EXPIRED:
                await session.delete(item)  # просрочка: удаляем из базы
            else:
                item.notify_stage = stage
            await session.commit()


async def safe_check(bot: Bot):
    try:
        await check_expiring_items(bot)
    except Exception:
        logger.exception("Expiry check failed")


# --- ГЛАВНАЯ ФУНКЦИЯ ---
async def main():
    bot = Bot(token=config.bot_token)
    dp = Dispatcher()

    dp.include_router(start.router)
    dp.include_router(items.router)
    dp.include_router(clear.router)

    await init_db()

    scheduler = AsyncIOScheduler(timezone="Europe/Moscow")
    scheduler.add_job(safe_check, "cron", hour=9, minute=0, args=(bot,))  # раз в день в 09:00
    scheduler.start()

    await web_server()

    # Проверка сразу при старте, чтобы не ждать до утра (например, после перезапуска на Render)
    startup_check = asyncio.create_task(safe_check(bot))

    await bot.delete_webhook(drop_pending_updates=True)
    try:
        await dp.start_polling(bot)
    finally:
        startup_check.cancel()


if __name__ == "__main__":
    asyncio.run(main())