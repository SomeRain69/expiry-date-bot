import asyncio
import os
from aiogram import Bot, Dispatcher
from aiohttp import web
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select
from datetime import datetime

from config import config
from database.database import init_db, async_session_maker
from handlers import start, items, clear
from database.models import ItemModel


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
    async with async_session_maker() as session:
        result = await session.execute(select(ItemModel))
        items_list = result.scalars().all()

        today = datetime.now().date()
        for item in items_list:
            if item.expires_at:
                try:
                    exp_date = item.expires_at
                    delta = (exp_date - today).days

                    if delta <= 14 and item.notified_14_days == 0:
                        if delta > 0:
                            msg = f"⚠️ <b>Внимание!</b> У товара <b>«{item.name}»</b> истекает срок годности через {delta} дн. (годен до {exp_date.strftime('%d.%m.%Y')})."
                        elif delta == 0:
                            msg = f"🚨 <b>Внимание!</b> У товара <b>«{item.name}»</b> срок годности истекает <b>сегодня</b> ({exp_date.strftime('%d.%m.%Y')})!"
                        else:
                            msg = f"❌ <b>Просрочка!</b> У товара <b>«{item.name}»</b> истек срок годности {exp_date.strftime('%d.%m.%Y')}!"

                        await bot.send_message(item.user_id, msg, parse_mode="HTML")
                        item.notified_14_days = 1
                        await session.commit()
                except Exception:
                    # Безопасно пропускаем, если пользователь заблокировал бота
                    pass


# --- ГЛАВНАЯ ФУНКЦИЯ ---
async def main():
    bot = Bot(token=config.bot_token)
    dp = Dispatcher()

    dp.include_router(start.router)
    dp.include_router(items.router)
    dp.include_router(clear.router)

    await init_db()

    scheduler = AsyncIOScheduler(timezone="Europe/Moscow")
    scheduler.add_job(check_expiring_items, "interval", hours=6, args=(bot,))  # Проверка раз в 6 часов
    scheduler.start()

    await web_server()

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())