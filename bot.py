import os
import logging
from typing import Final

from fastapi import FastAPI, Request, HTTPException
import uvicorn

from aiogram import Bot, Dispatcher, Router, types, F
from aiogram.filters import CommandStart, Text
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest

# ----------------- НАЛАШТУВАННЯ -----------------
logging.basicConfig(level=logging.INFO)
BOT_TOKEN: Final = os.getenv("BOT_TOKEN", "").strip()
BASE_URL:  Final = os.getenv("BASE_URL", "").strip().rstrip("/")
WEBHOOK_SECRET: Final = os.getenv("WEBHOOK_SECRET", "katars3es_42")

if not BOT_TOKEN or not BASE_URL:
    raise RuntimeError("Вкажи BOT_TOKEN і BASE_URL у змінних середовища")

bot = Bot(BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
r = Router()
dp.include_router(r)

app = FastAPI(title="Katarsees Assistant")

WEBHOOK_PATH = f"/webhook/{WEBHOOK_SECRET}"
WEBHOOK_URL = f"{BASE_URL}{WEBHOOK_PATH}"


# ----------------- КЛАВІАТУРИ -----------------
def main_inline_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔮 Діагностика", callback_data="act:diag"),
            InlineKeyboardButton(text="💵 Оплата", callback_data="act:pay"),
        ],
        [
            InlineKeyboardButton(text="📚 Навчання", callback_data="act:study"),
            InlineKeyboardButton(text="🗓️ Запис на консультацію", callback_data="act:consult"),
        ],
        [
            InlineKeyboardButton(text="📝 Запис на курс", callback_data="act:course"),
            InlineKeyboardButton(text="⬅️ Назад", callback_data="nav:back"),
        ],
    ])


# ----------------- ХЕНДЛЕРИ -----------------
WELCOME_TEXT = (
    "Вітаю! Обери дію нижче 👇\n\n"
    "Якщо кнопки не працюють — натисни /start ще раз."
)

@r.message(CommandStart())
async def on_start(m: types.Message):
    await m.answer(WELCOME_TEXT, reply_markup=main_inline_kb())

# універсальна відповідь + повернення меню
async def _answer_and_menu(message: types.Message, text: str):
    await message.answer(text)
    await message.answer("Що робимо далі?", reply_markup=main_inline_kb())

# callback-и (НЕ залежать від тексту кнопок)
@r.callback_query(Text(startswith="act:"))
async def on_action(cb: types.CallbackQuery):
    action = cb.data.split(":", 1)[1]
    await cb.answer()  # прибрати "loading"
    if action == "diag":
        await _answer_and_menu(cb.message, "🔮 Діагностика: напишіть коротко запит або натисніть /start, щоб обрати інше.")
    elif action == "pay":
        await _answer_and_menu(cb.message, "💵 Оплата: реквізити та умови надішлю окремо після підтвердження заявки.")
    elif action == "study":
        await _answer_and_menu(cb.message, "📚 Навчання: курс триває 8 міс (група) або 3 міс (індивідуально).")
    elif action == "consult":
        await _answer_and_menu(cb.message, "🗓️ Запис на консультацію: напишіть зручний день/час, я підберу слот.")
    elif action == "course":
        await _answer_and_menu(cb.message, "📝 Запис на курс: залиште ім'я, нік у Telegram/Instagram і коротку мотивацію.")
    else:
        await _answer_and_menu(cb.message, "Команда не розпізнана. Спробуй ще раз.")

@r.callback_query(Text("nav:back"))
async def on_back(cb: types.CallbackQuery):
    await cb.answer()
    try:
        await cb.message.edit_text(WELCOME_TEXT, reply_markup=main_inline_kb())
    except TelegramBadRequest:
        # якщо вже редагували — просто надішлемо нове
        await cb.message.answer(WELCOME_TEXT, reply_markup=main_inline_kb())

# fallback на будь-який текст
@r.message(F.text)
async def on_text(m: types.Message):
    logging.info(f"text from {m.from_user.id}: {m.text!r}")
    await m.answer("Я вас почула. Скористайтесь меню нижче 👇", reply_markup=main_inline_kb())


# ----------------- ВЕБХУК -----------------
@app.on_event("startup")
async def on_startup():
    # гарантовано прибираємо старі вебхуки/пулинги і ставимо один актуальний
    await bot.delete_webhook(drop_pending_updates=True)
    await bot.set_webhook(WEBHOOK_URL)
    info = await bot.get_webhook_info()
    logging.info(f"Webhook set to: {info.url}")

@app.on_event("shutdown")
async def on_shutdown():
    await bot.session.close()

@app.get("/health")
async def health():
    return {"ok": True, "webhook": WEBHOOK_URL}

@app.post(WEBHOOK_PATH)
async def telegram_webhook(request: Request):
    # простий захист: тільки наш шлях з SECRET
    try:
        update = types.Update.model_validate(await request.json(), context={"bot": bot})
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Bad request: {e}")
    await dp.feed_update(bot, update)
    return {"ok": True}


# ----------------- ЛОКАЛЬНИЙ СТАРТ (за бажання) -----------------
if __name__ == "__main__":
    # Запуск локально: uvicorn main:app --host 0.0.0.0 --port 8000
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
