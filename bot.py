import os
import re
import sqlite3
import asyncio
import logging
from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import (
    Message, CallbackQuery,
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardRemove
)
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# ====== НАСТРОЙКИ ======
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ====== БАЗА ДАННЫХ ======
conn = sqlite3.connect("feedback.db")
cur = conn.cursor()
cur.execute("""
    CREATE TABLE IF NOT EXISTS feedbacks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER, username TEXT, name TEXT,
        phone TEXT, email TEXT, message TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
""")
conn.commit()

# ====== СОСТОЯНИЯ ======
class Form(StatesGroup):
    name = State()
    phone = State()
    email = State()
    message = State()
    confirm = State()

# ====== КЛАВИАТУРЫ ======
def start_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Оставить заявку", callback_data="leave_feedback")],
        [InlineKeyboardButton(text="📍 Контакты", callback_data="contacts")]
    ])

def phone_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📱 Поделиться контактом", request_contact=True)],
            [KeyboardButton(text="❌ Отмена")]
        ], resize_keyboard=True, one_time_keyboard=True
    )

def skip_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="⏭ Пропустить")],
            [KeyboardButton(text="❌ Отмена")]
        ], resize_keyboard=True, one_time_keyboard=True
    )

def confirm_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Подтвердить", callback_data="confirm"),
         InlineKeyboardButton(text="🔄 Заново", callback_data="restart")]
    ])

def back_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_menu")]
    ])

# ====== БОТ ======
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
router = Router()
dp.include_router(router)

WELCOME = """
🏢 <b>Добро пожаловать!</b>

Мы рады, что вы обратились к нам.

📞 Оставьте свои контактные данные, и наш менеджер свяжется с вами!

👇 Нажмите кнопку ниже, чтобы начать.
"""

# ====== ХЕНДЛЕРЫ ======

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    logger.info(f"START от {message.from_user.id}")
    await state.clear()
    await message.answer(WELCOME, parse_mode="HTML", reply_markup=start_kb())

@router.message(F.text == "❌ Отмена")
async def cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Отменено.", reply_markup=ReplyKeyboardRemove())
    await message.answer(WELCOME, parse_mode="HTML", reply_markup=start_kb())

@router.callback_query(F.data == "leave_feedback")
async def start_form(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    await state.set_state(Form.name)
    await callback.message.answer("👤 Введите ваше <b>имя</b>:", parse_mode="HTML")

@router.callback_query(F.data == "contacts")
async def contacts(callback: CallbackQuery):
    await callback.answer()
    await callback.message.answer(
        "📍 <b>Контакты</b>\n\n📞 +7 (999) 123-45-67\n📧 info@company.com",
        parse_mode="HTML", reply_markup=back_kb()
    )

@router.callback_query(F.data == "back_to_menu")
async def back(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    await callback.message.answer(WELCOME, parse_mode="HTML", reply_markup=start_kb())

# --- Имя ---
@router.message(Form.name)
async def get_name(message: Message, state: FSMContext):
    if not message.text or len(message.text.strip()) < 2:
        await message.answer("⚠️ Введите имя (минимум 2 буквы):")
        return
    await state.update_data(name=message.text.strip())
    await state.set_state(Form.phone)
    await message.answer(
        "📱 Введите <b>номер телефона</b> или нажмите кнопку:",
        parse_mode="HTML", reply_markup=phone_kb()
    )

# --- Телефон (кнопка) ---
@router.message(Form.phone, F.contact)
async def get_phone_contact(message: Message, state: FSMContext):
    await state.update_data(phone=message.contact.phone_number)
    await state.set_state(Form.email)
    await message.answer(
        "📧 Введите <b>email</b> или нажмите «Пропустить»:",
        parse_mode="HTML", reply_markup=skip_kb()
    )

# --- Телефон (текст) ---
@router.message(Form.phone)
async def get_phone_text(message: Message, state: FSMContext):
    if not message.text:
        await message.answer("⚠️ Введите номер телефона:", reply_markup=phone_kb())
        return
    phone = message.text.strip()
    if not re.match(r'^[\+]?[0-9\s\-\(\)]{7,15}$', phone):
        await message.answer("⚠️ Неверный формат. Пример: +79991234567", reply_markup=phone_kb())
        return
    await state.update_data(phone=phone)
    await state.set_state(Form.email)
    await message.answer(
        "📧 Введите <b>email</b> или нажмите «Пропустить»:",
        parse_mode="HTML", reply_markup=skip_kb()
    )

# --- Email ---
@router.message(Form.email, F.text == "⏭ Пропустить")
async def skip_email(message: Message, state: FSMContext):
    await state.update_data(email="Не указан")
    await state.set_state(Form.message)
    await message.answer(
        "💬 Оставьте <b>сообщение</b> или нажмите «Пропустить»:",
        parse_mode="HTML", reply_markup=skip_kb()
    )

@router.message(Form.email)
async def get_email(message: Message, state: FSMContext):
    if not message.text:
        await message.answer("⚠️ Введите email:", reply_markup=skip_kb())
        return
    email = message.text.strip()
    if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
        await message.answer("⚠️ Неверный email. Попробуйте ещё:", reply_markup=skip_kb())
        return
    await state.update_data(email=email)
    await state.set_state(Form.message)
    await message.answer(
        "💬 Оставьте <b>сообщение</b> или нажмите «Пропустить»:",
        parse_mode="HTML", reply_markup=skip_kb()
    )

# --- Сообщение ---
@router.message(Form.message, F.text == "⏭ Пропустить")
async def skip_msg(message: Message, state: FSMContext):
    await state.update_data(msg="Не указано")
    await show_confirm(message, state)

@router.message(Form.message)
async def get_msg(message: Message, state: FSMContext):
    if not message.text:
        await message.answer("⚠️ Введите сообщение:", reply_markup=skip_kb())
        return
    await state.update_data(msg=message.text.strip())
    await show_confirm(message, state)

async def show_confirm(message: Message, state: FSMContext):
    data = await state.get_data()
    await state.set_state(Form.confirm)
    text = (
        f"📋 <b>Проверьте данные:</b>\n\n"
        f"👤 Имя: {data['name']}\n"
        f"📱 Телефон: {data['phone']}\n"
        f"📧 Email: {data['email']}\n"
        f"💬 Сообщение: {data['msg']}\n\n"
        f"Всё верно?"
    )
    await message.answer(text, parse_mode="HTML", reply_markup=confirm_kb())

# --- Подтвердить ---
@router.callback_query(Form.confirm, F.data == "confirm")
async def do_confirm(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await callback.answer("✅ Отправлено!")

    cur.execute(
        "INSERT INTO feedbacks (user_id,username,name,phone,email,message) VALUES (?,?,?,?,?,?)",
        (callback.from_user.id, callback.from_user.username or "",
         data['name'], data['phone'], data['email'], data['msg'])
    )
    conn.commit()

    await callback.message.answer(
        f"✅ <b>Спасибо за обращение!</b>\n\n"
        f"👤 {data['name']}\n📱 {data['phone']}\n"
        f"📧 {data['email']}\n💬 {data['msg']}\n\n"
        f"Наш менеджер свяжется с вами! 😊",
        parse_mode="HTML", reply_markup=ReplyKeyboardRemove()
    )

    if ADMIN_CHAT_ID:
        try:
            await bot.send_message(
                int(ADMIN_CHAT_ID),
                f"🔔 <b>Новая заявка!</b>\n\n"
                f"👤 {data['name']}\n📱 {data['phone']}\n"
                f"📧 {data['email']}\n💬 {data['msg']}\n"
                f"🆔 @{callback.from_user.username or 'нет'}",
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Ошибка уведомления админа: {e}")

    await callback.message.answer(WELCOME, parse_mode="HTML", reply_markup=start_kb())
    await state.clear()

# --- Заново ---
@router.callback_query(Form.confirm, F.data == "restart")
async def do_restart(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    await state.set_state(Form.name)
    await callback.message.answer("👤 Введите ваше <b>имя</b>:", parse_mode="HTML")

# ====== ЗАПУСК ======
async def main():
    logger.info("✅ Бот запускается...")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
