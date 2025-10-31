import os
import logging
from fastapi import FastAPI, Request
import httpx
from aiogram import Bot, Dispatcher, types, Router
from aiogram.filters import Command, Text

# ------- Налаштування & логування -------
logging.basicConfig(level=logging.INFO)
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")  # можна пустим, якщо не потрібно
BASE_URL = os.getenv("BASE_URL")  # напр. https://katarsees-bot-xxxx.onrender.com (без / в кінці)
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")  # будь-який рядок, ідентичний у ENV і в URL

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
router = Router()
dp.include_router(router)

app = FastAPI()

# ------- Кнопки -------
def main_kb():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("🔮 Діагностика", "💰 Оплата")
    kb.add("📚 Навчання")
    kb.add("🗓️ Запис на консультацію")
    return kb

# ------- Обробники (v3 синтаксис) -------
@router.message(Command("start"))
async def start_cmd(message: types.Message):
    await message.answer("Привіт! Обери, що тебе цікавить 👇", reply_markup=main_kb())

@router.message(Text("🔮 Діагностика"))
async def diag_cmd(message: types.Message):
    await message.answer("🪄 Напиши коротко, що тебе турбує — я передам Katarsees 🔥")

@router.message(Text("💰 Оплата"))
async def pay_cmd(message: types.Message):
    await message.answer("💵 Після підтвердження заявки надішлю реквізити для оплати.")

@router.message(Text("📚 Навчання"))
async def learn_cmd(message: types.Message):
    await message.answer("🧙‍♀️ Обери формат: повний курс / група / один урок.")

@router.message(Text("🗓️ Запис на консультацію"))
async def consult_cmd(message: types.Message):
    await message.answer("🪞 Напиши своє ім’я та коротко тему — і ми погодимо час.")

# ------- Вебхук -------
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
        # спершу обнуляємо
        await client.get(f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook")
        # і ставимо новий
        r = await client.get(
            f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook",
            params={"url": webhook_url}
        )
        logging.info("SetWebhook response: %s", r.text)
    logging.info("Webhook set to: %s", webhook_url)
