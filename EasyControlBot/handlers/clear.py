import html
from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select, delete

from database.database import async_session_maker
from database.models import ItemModel
from handlers.start import get_main_menu_keyboard

router = Router()


# Меню выбора сетки удаления (по 2 в ряд)
@router.callback_query(F.data == "start_delete_menu")
async def open_deletion_grid(callback: CallbackQuery):
    async with async_session_maker() as session:
        result = await session.execute(
            select(ItemModel)
            .where(ItemModel.user_id == callback.from_user.id)
            .order_by(ItemModel.expires_at.asc())
        )
        items = result.scalars().all()
        
        if not items:
            await callback.answer("Нет товаров для удаления!", show_alert=True)
            return

        builder = InlineKeyboardBuilder()
        for item in items:
            safe_name = html.escape(item.name)
            builder.button(text=f"❌ {safe_name}", callback_data=f"del_item_{item.id}")
        
        builder.adjust(2)
        builder.row(InlineKeyboardButton(text="⬅️ Назад к списку", callback_data="back_to_items"))

        await callback.message.edit_text(
            "Выберите товар для удаления:", 
            reply_markup=builder.as_markup()
        )
        await callback.answer()


# Безопасное удаление конкретного товара
@router.callback_query(F.data.startswith("del_item_"))
async def delete_specific_item(callback: CallbackQuery):
    item_id = int(callback.data.split("_")[-1])
    
    async with async_session_maker() as session:
        # ЗАЩИТА: удаляем только если товар принадлежит текущему пользователю
        item = await session.scalar(
            select(ItemModel).where(ItemModel.id == item_id, ItemModel.user_id == callback.from_user.id)
        )
        if item:
            await session.delete(item)
            await session.commit()
            await callback.answer("Товар успешно удален!", show_alert=True)
        else:
            await callback.answer("Товар не найден!", show_alert=True)
            return

        # Обновляем сетку удаления или возвращаем в список, если пусто
        result = await session.execute(
            select(ItemModel)
            .where(ItemModel.user_id == callback.from_user.id)
            .order_by(ItemModel.expires_at.asc())
        )
        items = result.scalars().all()
        
        if not items:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="btn_back_to_menu")]
            ])
            await callback.message.edit_text("📦 Список товаров пуст.", reply_markup=keyboard)
            return

        builder = InlineKeyboardBuilder()
        for item in items:
            safe_name = html.escape(item.name)
            builder.button(text=f"❌ {safe_name}", callback_data=f"del_item_{item.id}")
        
        builder.adjust(2)
        builder.row(InlineKeyboardButton(text="⬅️ Назад к списку", callback_data="back_to_items"))

        await callback.message.edit_text(
            "Выберите товар для удаления:", 
            reply_markup=builder.as_markup()
        )


# Кнопка возврата из сетки удаления обратно к списку товаров
@router.callback_query(F.data == "back_to_items")
async def return_to_items_list(callback: CallbackQuery):
    async with async_session_maker() as session:
        result = await session.execute(
            select(ItemModel)
            .where(ItemModel.user_id == callback.from_user.id)
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


# Очистка всего списка (кнопка из главного меню)
@router.callback_query(F.data == "btn_clear")
async def clear_confirm(callback: CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да, очистить всё", callback_data="confirm_clear")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="btn_back_to_menu")]
    ])
    await callback.message.edit_text("⚠️ Вы уверены, что хотите полностью очистить весь список товаров?",
                                     reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data == "confirm_clear")
async def clear_execute(callback: CallbackQuery):
    user_id = callback.from_user.id
    async with async_session_maker() as session:
        await session.execute(delete(ItemModel).where(ItemModel.user_id == user_id))
        await session.commit()

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ В главное меню", callback_data="btn_back_to_menu")]
    ])
    await callback.message.edit_text("🗑 Весь список товаров успешно очищен!", reply_markup=keyboard)
    await callback.answer()