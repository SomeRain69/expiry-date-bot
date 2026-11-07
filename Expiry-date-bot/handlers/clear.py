from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy import delete

from database.database import async_session_maker
from database.models import ItemModel
from handlers.start import get_main_menu_keyboard

router = Router()


@router.callback_query(F.data == "btn_clear")
async def clear_confirm(callback: CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да, очистить всё", callback_data="confirm_clear")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="btn_back_to_menu")]
    ])
    if isinstance(callback.message, Message):
        await callback.message.edit_text(
            "⚠️ Вы уверены, что хотите полностью очистить весь список товаров?",
            reply_markup=keyboard
        )
    await callback.answer()


@router.callback_query(F.data == "confirm_clear")
async def clear_execute(callback: CallbackQuery):
    user_id = callback.from_user.id
    async with async_session_maker() as session:
        await session.execute(delete(ItemModel).where(ItemModel.user_id == user_id))
        await session.commit()

    if isinstance(callback.message, Message):
        await callback.message.edit_text(
            "🗑 Весь список товаров успешно очищен!",
            reply_markup=get_main_menu_keyboard()
        )
    await callback.answer()