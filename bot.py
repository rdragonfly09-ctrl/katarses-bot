import os
import logging
from typing import Dict, Tuple

from fastapi import FastAPI, Request
import httpx

from aiogram import Bot, Dispatcher, Router, types
from aiogram.filters import Command, Text
from aiogram.fsm.storage.memory import MemoryStorage

# ----------------- БАЗА -----------------
logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))  # твій numeric ID
BASE_URL = os.getenv("BASE_URL")            # напр. https://katarsees-bot-xxxx.onrender.com (без / в кінці)
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "katars3es_42")  # будь-який рядок, але той самий і в ENV

bot = Bot(BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
r = Router()
dp.include_router(r)

app = FastAPI()

# in-memory «CRM» для відповідей адміна: key=admin_msg_id, val=(user_id, user_msg_id)
ADMIN_LINKS: Dict[int, Tuple[int, int]] = {}

# ----------------- КНОПКИ -----------------
def main_kb():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("🔮 Діагностика", "💰 Оплата")
    kb.add("📚 Навчання")
    kb.add("🗓️ Запис на консультацію")
    return kb

# ----------------- ХЕЛПЕРИ -----------------
async def send_admin_application(msg: types.Message, kind: str):
    """Надсилає заявку в адмін із інлайн-кнопками"""
    user = msg.from_user
    title = "🔔 Нова заявка" if kind != "діагностика" else "🔔 Нова заявка (діагностика)"
    text = (
        f"{title}!\n"
        f"👤 Ім’я: {user.full_name}\n"
        f"🆔 ID: {user.id}\n"
        f"📣 Користувач: {user.username and '@'+user.username or '—'}\n"
        f"🖊️ Текст: {msg.text}"
    )

    kb = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="✅ Прийняти", callback_data="adm_accept"),
         types.InlineKeyboardButton(text="❌ Відхилити", callback_data="adm_reject")],
        [types.InlineKeyboardButton(text="❓ Питання", callback_data="adm_ask")]
    ])

    admin_sent = await bot.send_message(ADMIN_ID, text, reply_markup=kb)
    ADMIN_LINKS[admin_sent.message_id] = (msg.chat.id, msg.message_id)

# ----------------- ХЕНДЛЕРИ -----------------
@r.message(Command("start"))
async def start(message: types.Message):
    await message.answer(
        "Привіт! Я *Katarsees Assistant*. Обери, що тебе цікавить 👇",
        reply_markup=main_kb(),
        parse_mode="Markdown",
    )

@r.message(Text("🔮 Діагностика"))
async def m_diag(message: types.Message):
    await message.answer(
        "✨ Напиши коротко, що тебе турбує — я передам повідомлення Katarsees.",
        reply_markup=main_kb()
    )

@r.message(Text("💰 Оплата"))
async def m_pay(message: types.Message):
    await message.answer(
        "💵 Після підтвердження заявки надішлю конкретні реквізити для оплати.",
        reply_markup=main_kb()
    )

@r.message(Text("📚 Навчання"))
async def m_learn(message: types.Message):
    await message.answer(
        "📚 Обери формат: повний курс / група / один урок. Напиши в одному повідомленні.",
        reply_markup=main_kb()
    )

@r.message(Text("🗓️ Запис на консультацію"))
async def m_consult(message: types.Message):
    await message.answer(
        "🗓️ Напиши *одним* повідомленням:\n"
        "• Ім’я\n"
        "• @нік або телефон\n"
        "• Що потрібно (діагностика/навчання/інше)\n"
        "• Короткий опис запиту",
        parse_mode="Markdown",
        reply_markup=main_kb()
    )

# Будь-який інший текст — трактуємо як заявку
@r.message()
async def any_text(message: types.Message):
    # Щоб було «як у Спілці» — все, що користувач написав, іде як заявка
    await message.answer("Дякую! Заявку/повідомлення надіслано. Очікуйте відповіді 🕯️")
    await send_admin_application(message, kind="звичайна")

# ----------------- АДМІН КНОПКИ -----------------
@r.callback_query(Text("adm_accept"))
async def cb_accept(cb: types.CallbackQuery):
    link = ADMIN_LINKS.get(cb.message.message_id)
    if not link:
        await cb.answer("Нема прив’язки до заявки (ймовірно перезапуск).", show_alert=True)
        return
    user_id, _ = link
    await bot.send_message(user_id, "✅ Заявку прийнято. Katarsees зв’яжеться з вами найближчим часом 🕯️")
    await cb.answer("Відповідь надіслано.")
    await cb.message.edit_reply_markup()  # прибрати кнопки

@r.callback_query(Text("adm_reject"))
async def cb_reject(cb: types.CallbackQuery):
    link = ADMIN_LINKS.get(cb.message.message_id)
    if not link:
        await cb.answer("Нема прив’язки до заявки (ймовірно перезапуск).", show_alert=True)
        return
    user_id, _ = link
    await bot.send_message(user_id, "❌ Заявку відхилено. Дякуємо за звернення.")
    await cb.answer("Відповідь надіслано.")
    await cb.message.edit_reply_markup()

@r.callback_query(Text("adm_ask"))
async def cb_ask(cb: types.CallbackQuery):
    link = ADMIN_LINKS.get(cb.message.message_id)
    if not link:
        await cb.answer("Нема прив’язки до заявки (ймовірно перезапуск).", show_alert=True)
        return
    user_id, _ = link
    await bot.send_message(
        user_id,
        "❓ Потрібні уточнення: будь ласка, надішліть додаткові деталі у відповідь на це повідомлення."
    )
    await cb.answer("Запит надіслано.")
    await cb.message.edit_reply_markup()

# ----------------- ВЕБХУК -----------------
@app.post(f"/webhook/{WEBHOOK_SECRET}")
async def webhook(request: Request):
    data = await request.json()
    logging.info("Incoming update: %s", data)
    update = types.Update(**data)
    await dp.feed_update(bot, update)
    return {"ok": True}

@app.on_event("startup")
async def on_startup():
    webhook_url = f"{BASE_URL}/webhook/{WEBHOOK_SECRET}"
    async with httpx.AsyncClient() as client:
        await client.get(f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook")
        resp = await client.get(
            f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook",
            params={"url": webhook_url}
        )
        logging.info("SetWebhook: %s", resp.text)
    logging.info("Webhook set -> %s", webhook_url)
