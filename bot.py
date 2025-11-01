import os
import logging
from typing import Final

from fastapi import FastAPI, Request, HTTPException
import uvicorn

from aiogram import Bot, Dispatcher, Router, types, F
from aiogram.filters import CommandStart
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest

# ----------------- НАЛАШТУВАННЯ -----------------
logging.basicConfig(level=logging.INFO)

BOT_TOKEN: Final = os.getenv("BOT_TOKEN", "").strip()
BASE_URL:  Final = os.getenv("BASE_URL", "").strip().rstrip("/")
WEBHOOK_SECRET: Final = os.getenv("WEBHOOK_SECRET", "katars3es_42")

if not BOT_TOKEN or not BASE_URL:
    # Робимо зрозумілу помилку в логах Render
    raise RuntimeError("Вкажи змінні середовища BOT_TOKEN і BASE_URL")

bot = Bot(BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
r = Router()
dp.include_router(r)

app = FastAPI(title="Katarsees Assistant")

WEBHOOK_PATH = f"/webhook/{WEBHOOK_SECRET}"
WEBHOOK_URL = f"{BASE_URL}{WEBHOOK_PATH}"

# ----------------- КЛАВІАТУРА -----------------
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

WELCOME_TEXT = (
    "Вітаю! Обери дію нижче 👇\n\n"
    "Якщо кнопки не працюють — натисни /start ще раз."
)

# ----------------- ХЕНДЛЕРИ -----------------
@r.message(CommandStart())
async def on_start(m: types.Message):
    await m.answer(WELCOME_TEXT, reply_markup=main_inline_kb())

async def _answer_and_menu(message: types.Message, text: str):
    await message.answer(text)
    await message.answer("Що робимо далі?", reply_markup=main_inline_kb())

# Фільтруємо callback-и без 'Text': через F.data.startswith(...)
@r.callback_query(F.data.startswith("act:"))
async def on_action(cb: types.CallbackQuery):
    action = cb.data.split(":", 1)[1]
    await cb.answer()
    if action == "diag":
        await _answer_and_menu(cb.message, "🔮 Діагностика: напишіть коротко запит або натисніть /start, щоб обрати інше.")
    elif action == "pay":
        await _answer_and_menu(cb.message, "💵 Оплата: реквізити та умови надішлю після підтвердження заявки.")
    elif action == "study":
        await _answer_and_menu(cb.message, "📚 Навчання: курс — група 8 міс, індивідуально 3 міс.")
    elif action == "consult":
        await _answer_and_menu(cb.message, "🗓️ Запис на консультацію: напишіть зручний день/час, я підберу слот.")
    elif action == "course":
        await _answer_and_menu(cb.message, "📝 Запис на курс: залиште ім'я, нік у TG/IG і коротку мотивацію.")
    else:
        await _answer_and_menu(cb.message, "Команда не розпізнана. Спробуй ще раз.")

@r.callback_query(F.data == "nav:back")
async def on_back(cb: types.CallbackQuery):
    await cb.answer()
    try:
        await cb.message.edit_text(WELCOME_TEXT, reply_markup=main_inline_kb())
    except TelegramBadRequest:
        await cb.message.answer(WELCOME_TEXT, reply_markup=main_inline_kb())

# Логування будь-яких текстів, щоб діагностувати “не ловиться”
@r.message(F.text)
async def on_text(m: types.Message):
    logging.info(f"text from {m.from_user.id}: {m.text!r}")
    await m.answer("Я вас почула. Скористайтесь меню нижче 👇", reply_markup=main_inline_kb())

# ----------------- ВЕБХУК -----------------
@app.on_event("startup")
async def on_startup():
    # Знімаємо старий вебхук (і глушимо “дубль-екземпляри”)
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
    try:
        update = types.Update.model_validate(await request.json(), context={"bot": bot})
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Bad request: {e}")
    await dp.feed_update(bot, update)
    return {"ok": True}

# ----------------- ЛОКАЛЬНИЙ ЗАПУСК -----------------
if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
