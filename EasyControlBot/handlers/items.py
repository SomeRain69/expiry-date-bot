import html
from datetime import datetime

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy import select, delete
from sqlalchemy.exc import IntegrityError

from config import TZ
from database.database import async_session_maker
from database.models import ItemModel
from handlers.start import get_main_menu_keyboard

router = Router()

MAX_NAME_LEN = 255


class AddItemState(StatesGroup):
    waiting_for_name = State()
    waiting_for_date = State()


def back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="btn_back_to_menu")]
    ])


# ---------- Шаг 1: название ----------
@router.callback_query(F.data == "btn_add")
async def start_add_item(callback: CallbackQuery, state: FSMContext):
    if isinstance(callback.message, Message):
        await callback.message.edit_text("✏️ Введите название товара:", reply_markup=back_keyboard())
    await state.set_state(AddItemState.waiting_for_name)
    await callback.answer()


@router.message(AddItemState.waiting_for_name, F.text)
async def process_item_name(message: Message, state: FSMContext):
    if message.from_user is None or message.text is None:
        return

    item_name = message.text.strip()
    user_id = message.from_user.id

    if not item_name:
        await message.answer("❌ Название не может быть пустым.")
        return

    if len(item_name) > MAX_NAME_LEN:
        await message.answer(f"❌ Слишком длинное название (максимум {MAX_NAME_LEN} символов).")
        return

    async with async_session_maker() as session:
        result = await session.execute(
            select(ItemModel).where(ItemModel.user_id == user_id, ItemModel.name == item_name)
        )
        existing_item = result.scalar_one_or_none()

    if existing_item:
        await message.answer(
            f"❌ Товар с названием <b>«{html.escape(item_name)}»</b> уже есть в вашей базе!",
            parse_mode="HTML"
        )
        return

    await state.update_data(item_name=item_name)
    await message.answer(
        "📅 Введите срок годности в формате <b>ДД.ММ.ГГГГ</b>:",
        reply_markup=back_keyboard(),
        parse_mode="HTML"
    )
    await state.set_state(AddItemState.waiting_for_date)


# ---------- Шаг 2: дата и сохранение ----------
@router.message(AddItemState.waiting_for_date, F.text)
async def process_item_date(message: Message, state: FSMContext):
    if message.from_user is None or message.text is None:
        return

    date_text = message.text.strip()

    try:
        exp_date = datetime.strptime(date_text, "%d.%m.%Y").date()
    except ValueError:
        await message.answer(
            "❌ Неверный формат даты! Пожалуйста, используйте формат <b>ДД.ММ.ГГГГ</b>.",
            parse_mode="HTML"
        )
        return

    today = datetime.now(TZ).date()
    if exp_date < today:
        await message.answer(
            "⚠️ Этот товар уже <b>просрочен</b>! Нельзя добавить товар с истекшим сроком годности.",
            parse_mode="HTML"
        )
        return

    data = await state.get_data()
    item_name = data.get("item_name")
    if not item_name:
        await state.clear()
        await message.answer("⚠️ Что-то пошло не так, начните заново.", reply_markup=get_main_menu_keyboard())
        return

    user_id = message.from_user.id

    try:
        async with async_session_maker() as session:
            session.add(ItemModel(
                user_id=user_id,
                name=item_name,
                expires_at=exp_date,
                notified_14_days=0
            ))
            await session.commit()
    except IntegrityError:
        # Защита от гонки: такой товар уже успели добавить
        await state.clear()
        await message.answer(
            f"❌ Товар <b>«{html.escape(item_name)}»</b> уже есть в вашей базе!",
            reply_markup=get_main_menu_keyboard(),
            parse_mode="HTML"
        )
        return

    await state.clear()
    await message.answer(
        f"✅ Товар <b>«{html.escape(item_name)}»</b> (годен до {exp_date.strftime('%d.%m.%Y')}) успешно добавлен!",
        reply_markup=get_main_menu_keyboard(),
        parse_mode="HTML"
    )


# ---------- Список товаров ----------
@router.callback_query(F.data == "btn_items")
async def show_items(callback: CallbackQuery):
    if not isinstance(callback.message, Message):
        await callback.answer()
        return

    user_id = callback.from_user.id
    async with async_session_maker() as session:
        result = await session.execute(
            select(ItemModel)
            .where(ItemModel.user_id == user_id)
            .order_by(ItemModel.expires_at.asc())
        )
        items = result.scalars().all()

    if not items:
        await callback.message.edit_text("📦 Ваш список товаров пока пуст.", reply_markup=back_keyboard())
        await callback.answer()
        return

    text = "📋 <b>Ваши товары:</b>\n\n"
    for item in items:
        text += f"▪️ <b>{html.escape(item.name)}</b> — годен до {item.expires_at.strftime('%d.%m.%Y')}\n"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗑 Удалить товар", callback_data="start_delete_menu")],
        [InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="btn_back_to_menu")]
    ])
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()


# ---------- Удаление ----------
async def render_delete_menu(message: Message, user_id: int):
    async with async_session_maker() as session:
        result = await session.execute(
            select(ItemModel)
            .where(ItemModel.user_id == user_id)
            .order_by(ItemModel.expires_at.asc())
        )
        items = result.scalars().all()

    if not items:
        await message.edit_text("📦 Ваш список товаров пока пуст.", reply_markup=back_keyboard())
        return

    buttons = [
        [InlineKeyboardButton(text=f"❌ {item.name[:40]}", callback_data=f"del_item_{item.id}")]
        for item in items
    ]
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="btn_items")])
    await message.edit_text(
        "Выберите товар для удаления:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )


@router.callback_query(F.data == "start_delete_menu")
async def start_delete_menu(callback: CallbackQuery):
    if isinstance(callback.message, Message):
        await render_delete_menu(callback.message, callback.from_user.id)
    await callback.answer()


@router.callback_query(F.data.startswith("del_item_"))
async def delete_single_item(callback: CallbackQuery):
    if callback.data is None or not isinstance(callback.message, Message):
        await callback.answer()
        return

    try:
        item_id = int(callback.data.split("_")[2])
    except (IndexError, ValueError):
        await callback.answer()
        return

    async with async_session_maker() as session:
        # Проверяем владельца: нельзя удалить чужой товар
        await session.execute(
            delete(ItemModel).where(
                ItemModel.id == item_id,
                ItemModel.user_id == callback.from_user.id
            )
        )
        await session.commit()

    await render_delete_menu(callback.message, callback.from_user.id)
    await callback.answer("🗑 Товар удалён")