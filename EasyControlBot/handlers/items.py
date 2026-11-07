import html
from datetime import datetime
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import select

from database.database import async_session_maker
from database.models import ItemModel
from handlers.start import get_main_menu_keyboard

router = Router()

class AddItemState(StatesGroup):
    waiting_for_name = State()
    waiting_for_date = State()


# Шаг 1: Добавление товара (название)
@router.callback_query(F.data == "btn_add")
async def start_add_item(callback: CallbackQuery, state: FSMContext):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="btn_back_to_menu")]
    ])
    await callback.message.answer("✏️ Введите название товара:", reply_markup=keyboard)
    await state.set_state(AddItemState.waiting_for_name)
    await callback.answer()


@router.message(AddItemState.waiting_for_name, F.text)
async def process_item_name(message: Message, state: FSMContext):
    item_name = message.text.strip()
    user_id = message.from_user.id

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
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="btn_back_to_menu")]
    ])
    await message.answer("📅 Введите срок годности в формате <b>ДД.ММ.ГГГГ</b>:", reply_markup=keyboard,
                         parse_mode="HTML")
    await state.set_state(AddItemState.waiting_for_date)


# Шаг 2: Ввод даты и сохранение товара в базу
@router.message(AddItemState.waiting_for_date, F.text)
async def process_item_date(message: Message, state: FSMContext):
    date_text = message.text.strip()

    try:
        exp_date = datetime.strptime(date_text, "%d.%m.%Y").date()
        today = datetime.now().date()

        if exp_date < today:
            await message.answer(
                "⚠️ Этот товар уже <b>просрочен</b>! Нельзя добавить товар с истекшим сроком годности.",
                parse_mode="HTML"
            )
            return

    except ValueError:
        await message.answer("❌ Неверный формат даты! Пожалуйста, используйте формат <b>ДД.ММ.ГГГГ</b>.",
                             parse_mode="HTML")
        return

    data = await state.get_data()
    item_name = data.get("item_name")
    user_id = message.from_user.id

    async with async_session_maker() as session:
        new_item = ItemModel(
            user_id=user_id,
            name=item_name,
            expires_at=exp_date,
            notified_14_days=0
        )
        session.add(new_item)
        await session.commit()

    await state.clear()
    await message.answer(
        f"✅ Товар <b>«{html.escape(item_name)}»</b> (годен до {date_text}) успешно добавлен!",
        reply_markup=get_main_menu_keyboard(),
        parse_mode="HTML"
    )


# Просмотр списка товаров (текст отдельно, кнопка управления отдельно)
@router.callback_query(F.data == "btn_items")
async def show_items(callback: CallbackQuery):
    user_id = callback.from_user.id
    async with async_session_maker() as session:
        result = await session.execute(
            select(ItemModel)
            .where(ItemModel.user_id == user_id)
            .order_by(ItemModel.expires_at.asc())
        )
        items = result.scalars().all()

        if not items:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="btn_back_to_menu")]
            ])
            await callback.message.edit_text("📦 Ваш список товаров пока пуст.", reply_markup=keyboard)
            await callback.answer()
            return

        text = "📋 <b>Ваши товары:</b>\n\n"
        for item in items:
            safe_name = html.escape(item.name)
            text += f"▪️ <b>{safe_name}</b> — годен до {item.expires_at.strftime('%d.%m.%Y')}\n"

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🗑 Удалить товар", callback_data="start_delete_menu")],
            [InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="btn_back_to_menu")]
        ])

        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
        await callback.answer()