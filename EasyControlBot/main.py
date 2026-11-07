import asyncio
import html
import logging
import os
from datetime import datetime

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


# --- ФОНОВАЯ ПРОВЕРКА СРОКОВ ГОДНОСТИ ---
async def check_expiring_items(bot: Bot):
    today = datetime.now(TZ).date()

    async with async_session_maker() as session:
        result = await session.execute(
            select(ItemModel).where(ItemModel.notified_14_days == 0)
        )
        pending = result.scalars().all()

        for item in pending:
            delta = (item.expires_at - today).days
            if delta > 14:
                continue

            name = html.escape(item.name)
            date_str = item.expires_at.strftime("%d.%m.%Y")

            if delta > 0:
                msg = f"⚠️ <b>Внимание!</b> У товара <b>«{name}»</b> истекает срок годности через {delta} дн. (годен до {date_str})."
            elif delta == 0:
                msg = f"🚨 <b>Внимание!</b> У товара <b>«{name}»</b> срок годности истекает <b>сегодня</b> ({date_str})!"
            else:
                msg = f"❌ <b>Просрочка!</b> У товара <b>«{name}»</b> истек срок годности {date_str}!"

            try:
                await bot.send_message(item.user_id, msg, parse_mode="HTML")
            except TelegramForbiddenError:
                # Пользователь заблокировал бота: повторять отправку бессмысленно
                logger.warning("User %s blocked the bot, skipping notification", item.user_id)
            except Exception:
                logger.exception("Failed to notify user %s about item %s", item.user_id, item.id)
                continue  # флаг не ставим, попробуем при следующей проверке

            item.notified_14_days = 1
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