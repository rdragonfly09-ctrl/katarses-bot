# bot.py
import os
from typing import Optional

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Update, Message, ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
)
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext

# ========= ENV =========
BOT_TOKEN: str = os.getenv("BOT_TOKEN", "").strip()
ADMIN_ID_RAW: str = os.getenv("ADMIN_ID", "").strip()
WEBHOOK_SECRET: str = os.getenv("WEBHOOK_SECRET", "").strip()

if not BOT_TOKEN:
    raise RuntimeError("Set BOT_TOKEN in Environment")
if not ADMIN_ID_RAW.isdigit():
    raise RuntimeError("Set ADMIN_ID (numeric Telegram ID) in Environment")
if not WEBHOOK_SECRET:
    raise RuntimeError("Set WEBHOOK_SECRET in Environment")

ADMIN_ID: int = int(ADMIN_ID_RAW)

# ========= AIOGRAM CORE =========
bot = Bot(BOT_TOKEN, parse_mode="HTML")
dp = Dispatcher(storage=MemoryStorage())
app = FastAPI()

# ========= KEYBOARDS =========
main_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🔮 Діагностика"), KeyboardButton(text="📚 Навчання")],
        [KeyboardButton(text="💰 Оплата")],
        [KeyboardButton(text="🗓️ Запис на консультацію")],
    ],
    resize_keyboard=True
)

back_kb = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="⬅️ Назад")]],
    resize_keyboard=True
)

def admin_decision_kb(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Прийняти", callback_data=f"decide:ok:{user_id}"),
            InlineKeyboardButton(text="❌ Відхилити", callback_data=f"decide:no:{user_id}"),
        ],
        [
            InlineKeyboardButton(text="✍️ Уточнити", callback_data=f"decide:ask:{user_id}")
        ]
    ])

# ========= STATES =========
class Form(StatesGroup):
    waiting_request = State()   # клієнт пише одне повідомлення-заявку

# ========= BASIC HANDLERS =========
@dp.message(F.text == "/start")
async def cmd_start(msg: Message):
    await msg.answer(
        "Вітаю! Я асистент. Обери розділ нижче — або напиши повідомлення.",
        reply_markup=main_kb
    )

@dp.message(F.text == "⬅️ Назад")
async def go_back(msg: Message, state: FSMContext):
    await state.clear()
    await msg.answer("Повертаємось до головного меню:", reply_markup=main_kb)

@dp.message(F.text == "🔮 Діагностика")
async def diagnostics_info(msg: Message):
    text = (
        "✨ Напишіть коротко, що вас турбує — і я передам повідомлення Katarsees.\n"
        "Можна додати @username або телефон для звʼязку."
    )
    await msg.answer(text, reply_markup=back_kb)

@dp.message(F.text == "📚 Навчання")
async def education_info(msg: Message):
    text = (
        "📚 Навчання: повний курс / група / індивідуально / один урок.\n"
        "Напишіть формат, своє імʼя та @username/телефон — Katarsees відповість найближчим часом."
    )
    await msg.answer(text, reply_markup=back_kb)

@dp.message(F.text == "💰 Оплата")
async def payment_info(msg: Message):
    text = (
        "💳 Оплата: реквізити надсилаються індивідуально після узгодження формату.\n"
        "Напишіть свій запит або натисніть «🗓️ Запис на консультацію»."
    )
    await msg.answer(text, reply_markup=back_kb)

@dp.message(F.text == "🗓️ Запис на консультацію")
async def start_request(msg: Message, state: FSMContext):
    await state.set_state(Form.waiting_request)
    text = (
        "📝 Напишіть ОДНИМ повідомленням:\n"
        "• Імʼя\n"
        "• @username або телефон\n"
        "• Що потрібно (діагностика/навчання/інше)\n"
        "• Короткий опис запиту\n\n"
        "Після надсилання — я передам заявку та повернуся з відповіддю 🕯️"
    )
    await msg.answer(text, reply_markup=back_kb)

# ловимо заявку
@dp.message(Form.waiting_request, F.text)
async def catch_request(msg: Message, state: FSMContext):
    await state.clear()

    user = msg.from_user
    uid = user.id
    uname = ("@" + user.username) if user.username else "—"
    full_name = user.full_name

    # повідомлення клієнту
    await msg.answer("Дякую! Заявку надіслано. Очікуйте відповіді 🕯️", reply_markup=main_kb)

    # повідомлення адмінові
    admin_text = (
        "🔔 <b>Нова заявка!</b>\n"
        f"👤 <b>Імʼя:</b> {full_name}\n"
        f"🆔 <b>ID:</b> <code>{uid}</code>\n"
        f"📣 <b>Користувач:</b> {uname}\n"
        f"🖋 <b>Текст:</b> {msg.text}"
    )

    try:
        await bot.send_message(
            ADMIN_ID, admin_text, reply_markup=admin_decision_kb(uid)
        )
    except Exception:
        # якщо ADMIN_ID невірний або бот не може написати адмінові
        pass

# універсальна відповідь на всякий текст поза станами
@dp.message()
async def fallback(msg: Message):
    await msg.answer("Я почув(ла) вас. Оберіть розділ нижче або натисніть «🗓️ Запис на консультацію».",
                     reply_markup=main_kb)

# ========= ADMIN CALLBACKS =========
@dp.callback_query(F.data.startswith("decide:"))
async def on_decide(cb: CallbackQuery):
    # дозволяємо натискати тільки адмінові
    if cb.from_user.id != ADMIN_ID:
        await cb.answer("Лише для адміністратора.", show_alert=True)
        return

    try:
        _, action, user_id_str = cb.data.split(":")
        target_id = int(user_id_str)
    except Exception:
        await cb.answer("Некоректні дані.", show_alert=True)
        return

    if action == "ok":
        await bot.send_message(target_id,
                               "✅ Заявку прийнято. Katarsees незабаром зʼявиться з деталями.")
        await cb.message.answer("✅ Відповідь клієнту надіслано.")
        await cb.answer()
    elif action == "no":
        await bot.send_message(target_id,
                               "❌ На жаль, наразі не можу взяти вашу заявку. "
                               "Можна спробувати пізніше або уточнити формат.")
        await cb.message.answer("❌ Відповідь клієнту надіслано.")
        await cb.answer()
    elif action == "ask":
        await bot.send_message(target_id,
                               "✍️ Будь ласка, надішліть, що саме потрібно уточнити — і я передам Katarsees.")
        await cb.message.answer("✍️ Запит на уточнення надіслано клієнту.")
        await cb.answer()
    else:
        await cb.answer("Невідома дія.", show_alert=True)

# ========= FASTAPI =========
@app.get("/")
async def root():
    return {"status": "ok"}

# ВАЖЛИВО: маршрут вебхука існує завжди → більше не буде 404
@app.post("/webhook/{secret:path}")
async def telegram_webhook(secret: str, request: Request):
    # якщо секрет не збігається — повертаємо 403 (а не 404),
    # щоб Telegram бачив існуючу кінцеву точку
    if secret != WEBHOOK_SECRET:
        return Response(status_code=403)

    data = await request.json()
    update = Update.model_validate(data, context={"bot": bot})
    await dp.feed_webhook_update(bot, update)
    return JSONResponse({"ok": True})
