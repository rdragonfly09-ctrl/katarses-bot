import os
from fastapi import FastAPI, Request, Response
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, Update

# === Конфігурація ===
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "katarsees123")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
app = FastAPI()

# === Хендлер команди /start ===
@dp.message(F.text == "/start")
async def start_command(message: Message):
    await message.answer("✨ Вітаю! Katarsees Assistant готовий до роботи.")

# === Хендлер вебхука ===
@app.post(f"/webhook/{WEBHOOK_SECRET}")
async def webhook(request: Request):
    try:
        data = await request.json()
        update = Update.model_validate(data)
        await dp.feed_update(bot, update)
    except Exception as e:
        print(f"Помилка у webhook: {e}")
    return Response(status_code=200)

# === Тестовий корінь для Render ===
@app.get("/")
async def root():
    return {"status": "bot is alive 💫"}

# === Локальний запуск (не потрібно на Render) ===
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=10000)
