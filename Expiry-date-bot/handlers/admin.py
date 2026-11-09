import html

from aiogram import Router, F
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import func, select

from config import config
from database.database import async_session_maker
from database.models import BotUser, ItemModel

router = Router()

# Все хендлеры этого роутера доступны только администратору
router.message.filter(F.from_user.id == config.admin_id)
router.callback_query.filter(F.from_user.id == config.admin_id)


def admin_keyboard(user_id: int, banned: bool) -> InlineKeyboardMarkup:
    if banned:
        button = InlineKeyboardButton(text="✅ Разблокировать", callback_data=f"adm_unban_{user_id}")
    else:
        button = InlineKeyboardButton(text="⛔ Заблокировать", callback_data=f"adm_ban_{user_id}")
    return InlineKeyboardMarkup(inline_keyboard=[[button]])


async def set_ban(user_id: int, banned: bool) -> None:
    async with async_session_maker() as session:
        user = await session.get(BotUser, user_id)
        if user is None:
            # Можно заблокировать заранее, даже если человек ещё не писал боту
            session.add(BotUser(user_id=user_id, is_banned=banned))
        else:
            user.is_banned = banned
        await session.commit()


def parse_user_id(command: CommandObject) -> int | None:
    if not command.args:
        return None
    try:
        return int(command.args.strip())
    except ValueError:
        return None


@router.message(Command("admin"))
async def cmd_admin(message: Message):
    await message.answer(
        "🛠 <b>Админ-панель</b>\n\n"
        "/users — последние пользователи и число их товаров\n"
        "/ban <code>ID</code> — заблокировать пользователя\n"
        "/unban <code>ID</code> — разблокировать\n\n"
        "О новых пользователях бот сообщает сам, с кнопкой блокировки.",
        parse_mode="HTML"
    )


@router.message(Command("ban"))
async def cmd_ban(message: Message, command: CommandObject):
    user_id = parse_user_id(command)
    if user_id is None:
        await message.answer("Использование: <code>/ban ID</code>", parse_mode="HTML")
        return
    if user_id == config.admin_id:
        await message.answer("Себя заблокировать нельзя 🙂")
        return

    await set_ban(user_id, True)
    await message.answer(f"⛔ Пользователь <code>{user_id}</code> заблокирован.", parse_mode="HTML")


@router.message(Command("unban"))
async def cmd_unban(message: Message, command: CommandObject):
    user_id = parse_user_id(command)
    if user_id is None:
        await message.answer("Использование: <code>/unban ID</code>", parse_mode="HTML")
        return

    await set_ban(user_id, False)
    await message.answer(f"✅ Пользователь <code>{user_id}</code> разблокирован.", parse_mode="HTML")


@router.message(Command("users"))
async def cmd_users(message: Message):
    async with async_session_maker() as session:
        total = (await session.execute(select(func.count()).select_from(BotUser))).scalar_one()
        users = (await session.execute(
            select(BotUser).order_by(BotUser.created_at.desc()).limit(30)
        )).scalars().all()
        counts = dict((await session.execute(
            select(ItemModel.user_id, func.count()).group_by(ItemModel.user_id)
        )).all())

    if not users:
        await message.answer("Пока никто не пользовался ботом.")
        return

    lines = [f"👥 <b>Пользователи</b> (показаны последние {len(users)} из {total}):\n"]
    for u in users:
        mark = "⛔" if u.is_banned else "✅"
        name = html.escape(u.first_name or "—")
        username = f"@{html.escape(u.username)}" if u.username else ""
        lines.append(f"{mark} <code>{u.user_id}</code> {name} {username} — товаров: {counts.get(u.user_id, 0)}")

    await message.answer("\n".join(lines), parse_mode="HTML")


@router.callback_query(F.data.startswith("adm_ban_") | F.data.startswith("adm_unban_"))
async def toggle_ban(callback: CallbackQuery):
    if callback.data is None:
        await callback.answer()
        return

    parts = callback.data.split("_")  # adm_ban_123 / adm_unban_123
    try:
        banned = parts[1] == "ban"
        user_id = int(parts[2])
    except (IndexError, ValueError):
        await callback.answer()
        return

    if user_id == config.admin_id:
        await callback.answer("Себя заблокировать нельзя", show_alert=True)
        return

    await set_ban(user_id, banned)

    if isinstance(callback.message, Message):
        await callback.message.edit_reply_markup(reply_markup=admin_keyboard(user_id, banned))
    await callback.answer("⛔ Заблокирован" if banned else "✅ Разблокирован")
