from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

router = Router()


def get_main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить товар", callback_data="btn_add")],
        [InlineKeyboardButton(text="📋 Мои товары", callback_data="btn_items")],
        [InlineKeyboardButton(text="🗑 Очистить список", callback_data="btn_clear")]
    ])


@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "👋 <b>Привет! Я бот для контроля сроков годности.</b>\n\nВыбери нужное действие:",
        reply_markup=get_main_menu_keyboard(),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "btn_back_to_menu")
async def back_to_menu(callback: CallbackQuery, state: FSMContext):
    # Сбрасываем FSM, чтобы следующий текст не приняли за название/дату товара
    await state.clear()
    if isinstance(callback.message, Message):
        await callback.message.edit_text(
            "👋 <b>Главное меню:</b>\n\nВыбери нужное действие:",
            reply_markup=get_main_menu_keyboard(),
            parse_mode="HTML"
        )
    await callback.answer()