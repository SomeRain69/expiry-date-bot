import html
import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject, User
from sqlalchemy.exc import IntegrityError

from config import config
from database.database import async_session_maker
from database.models import BotUser
from handlers.admin import admin_keyboard

logger = logging.getLogger(__name__)


class AccessMiddleware(BaseMiddleware):
    """Регистрирует каждого пользователя и не пускает заблокированных."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        tg_user: User | None = data.get("event_from_user")
        if tg_user is None or tg_user.is_bot:
            return await handler(event, data)

        is_admin = tg_user.id == config.admin_id
        is_new = False

        async with async_session_maker() as session:
            bot_user = await session.get(BotUser, tg_user.id)

            if bot_user is None:
                session.add(BotUser(
                    user_id=tg_user.id,
                    username=tg_user.username,
                    first_name=tg_user.first_name,
                ))
                try:
                    await session.commit()
                    is_new = True
                except IntegrityError:
                    # Два сообщения от нового пользователя пришли одновременно
                    await session.rollback()
                bot_user = await session.get(BotUser, tg_user.id)
            elif bot_user.username != tg_user.username or bot_user.first_name != tg_user.first_name:
                bot_user.username = tg_user.username
                bot_user.first_name = tg_user.first_name
                await session.commit()

            banned = bot_user is not None and bot_user.is_banned

        if is_new and not is_admin:
            await self._notify_admin(data["bot"], tg_user)

        # Администратор не блокируется никогда
        if banned and not is_admin:
            if isinstance(event, CallbackQuery):
                await event.answer("⛔ Доступ к боту закрыт", show_alert=True)
            elif isinstance(event, Message):
                await event.answer("⛔ Доступ к боту закрыт.")
            return None

        return await handler(event, data)

    @staticmethod
    async def _notify_admin(bot, tg_user: User) -> None:
        username = f"@{html.escape(tg_user.username)}" if tg_user.username else "нет username"
        text = (
            "👤 <b>Новый пользователь</b>\n\n"
            f"Имя: {html.escape(tg_user.full_name)}\n"
            f"Username: {username}\n"
            f"ID: <code>{tg_user.id}</code>"
        )
        try:
            await bot.send_message(
                config.admin_id, text,
                reply_markup=admin_keyboard(tg_user.id, banned=False),
                parse_mode="HTML",
            )
        except Exception:
            logger.exception("Failed to notify admin about new user %s", tg_user.id)
