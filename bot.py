# -*- coding: utf-8 -*-
# Katarsees Assistant — aiogram 2.x

# ==== НАЛАШТУВАННЯ (твій продакшн) ====
TOKEN       = "8490324981:AAE4f89VWfWmhYzLa_jBw0FVubGFObbvIzw"     # твій токен
ADMIN_ID    = 6958130111                                           # твій Telegram user_id
PAYMENT_LINK = "https://send.monobank.ua/jar/8tw85dr9Rb"           # посилання на оплату

# ==== ІМПОРТИ ====
import html
import csv
from datetime import datetime

from aiogram import Bot, Dispatcher, types
from aiogram.types import ParseMode, ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils import executor

# ==== ФАЙЛИ ЗАЯВОК ====
DIAG_CSV   = "leads.csv"          # діагностика
CONSULT_CSV= "consult_leads.csv"  # консультація
COURSE_CSV = "course_leads.csv"   # навчання

# ==== СТАНИ (простий трекер, без FSM) ====
awaiting_diag     = set()
awaiting_consult  = set()
awaiting_course   = set()

# ==== КЛАВІАТУРИ ====
def main_keyboard():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row(KeyboardButton("🔮 Діагностика"), KeyboardButton("💰 Оплата"))
    kb.row(KeyboardButton("📚 Навчання"))
    kb.row(KeyboardButton("🗓️ Запис на консультацію"))
    return kb

def learning_keyboard():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("📝 Запис на курс"))
    kb.add(KeyboardButton("⬅️ Назад"))
    return kb

# ==== ХЕЛПЕРИ ====
def admin_user_line(user: types.User) -> str:
    uname = f"@{user.username}" if user.username else "—"
    full  = user.full_name or "—"
    return f"{full}, {uname}"

def ensure_csv_header(filename: str, header: list):
    try:
        with open(filename, "r", encoding="utf-8-sig"):
            pass
    except FileNotFoundError:
        with open(filename, "w", newline="", encoding="utf-8-sig") as f:
            csv.writer(f).writerow(header)

def save_lead(filename: str, user: types.User, text: str, source: str):
    ensure_csv_header(
        filename,
        ["timestamp", "tg_id", "username", "full_name", "request", "source", "contact"]
    )
    with open(filename, "a", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow([
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            user.id,
            user.username or "",
            user.full_name or "",
            text,
            source,
            ""  # поле під контакт, лишаємо порожнім (можеш заповнювати пізніше)
        ])

async def notify_admin(kind: str, user: types.User, text: str, extra: str = ""):
    # Формуємо акуратне HTML-повідомлення адмінам
    html_msg = (
        f"🔔 <b>Нова заявка ({html.escape(kind)})!</b>\n"
        f"👤 Ім’я: {html.escape(user.full_name or '—')}\n"
        f"🆔 ID: <code>{user.id}</code>\n"
        f"🗣️ Користувач: {html.escape(admin_user_line(user))}\n"
        f"✍️ Текст: <i>{html.escape(text)}</i>\n"
    )
    if extra:
        html_msg += f"{extra}\n"
    await bot.send_message(ADMIN_ID, html_msg, parse_mode=ParseMode.HTML)

# ==== БОТ/ДИСПЕТЧЕР ====
bot = Bot(token=TOKEN, parse_mode=ParseMode.HTML)
dp  = Dispatcher(bot)

# ==== /start ====
@dp.message_handler(commands=["start"])
async def cmd_start(message: types.Message):
    await message.answer(
        "🌕 Вітаю! Я — помічниця Katarsees. Оберіть, що вас цікавить:",
        reply_markup=main_keyboard()
    )

# ==== ОПЛАТА ====
@dp.message_handler(lambda m: m.text == "💰 Оплата")
async def pay(message: types.Message):
    await message.answer(
        f"💳 Оплата: {PAYMENT_LINK}\n\nПісля оплати надішліть квитанцію 🌙",
    )

# ==== ДІАГНОСТИКА ====
@dp.message_handler(lambda m: m.text == "🔮 Діагностика")
async def diag(message: types.Message):
    awaiting_consult.discard(message.from_user.id)
    awaiting_course.discard(message.from_user.id)
    awaiting_diag.add(message.from_user.id)
    await message.answer(
        "✨ Напишіть коротко, що вас турбує. Я передам повідомлення Katarsees 🕯️"
    )

# ==== ЗАПИС НА КОНСУЛЬТАЦІЮ ====
@dp.message_handler(lambda m: m.text == "🗓️ Запис на консультацію")
async def consult(message: types.Message):
    awaiting_diag.discard(message.from_user.id)
    awaiting_course.discard(message.from_user.id)
    awaiting_consult.add(message.from_user.id)
    await message.answer(
        "📅 Щоб записатися на консультацію, напишіть зручний день і час.\n"
        "Katarsees підтвердить запис у повідомленні 🌙"
    )

# ==== НАВЧАННЯ ====
@dp.message_handler(lambda m: m.text == "📚 Навчання")
async def learning(message: types.Message):
    txt = (
        "✨ <b>Навчання Яснобачення і Ментальна магія</b>\n\n"
        "1️⃣ Повний курс (3 міс., індивідуально): <b>25 000₴</b>/міс\n"
        "2️⃣ Група (самостійне): <b>5 000₴</b>/міс\n"
        "3️⃣ Один урок: <b>1 000₴</b>\n\n"
        "Instagram-бонус: напишіть слово <b>INSTAZNIJKA</b> — і отримаєте знижку 🌙\n\n"
        "Щоб залишити заявку, натисніть «📝 Запис на курс»."
    )
    await message.answer(txt, reply_markup=learning_keyboard())

@dp.message_handler(lambda m: m.text == "📝 Запис на курс")
async def learning_register(message: types.Message):
    awaiting_diag.discard(message.from_user.id)
    awaiting_consult.discard(message.from_user.id)
    awaiting_course.add(message.from_user.id)
    await message.answer(
        "🧘 Вкажіть формат (повний курс / група / один урок), своє ім’я та @username або телефон.\n"
        "Katarsees зв’яжеться з вами найближчим часом 🌕"
    )

@dp.message_handler(lambda m: m.text == "⬅️ Назад")
async def go_back(message: types.Message):
    awaiting_diag.discard(message.from_user.id)
    awaiting_consult.discard(message.from_user.id)
    awaiting_course.discard(message.from_user.id)
    await message.answer("⬅️ Повертаємось до головного меню:", reply_markup=main_keyboard())

# ==== КЕЧ-ОЛЛ: приймає текст після вибору дії ====
@dp.message_handler(content_types=types.ContentTypes.TEXT)
async def catch_all_text(message: types.Message):
    uid = message.from_user.id
    txt = message.text.strip()

    # 1) Діагностика
    if uid in awaiting_diag:
        save_lead(DIAG_CSV, message.from_user, txt, "diagnostics")
        await notify_admin("діагностика", message.from_user, txt)
        awaiting_diag.discard(uid)
        await message.answer("✅ Дякую! Повідомлення передано Katarsees. Очікуйте відповідь 🌙", reply_markup=main_keyboard())
        return

    # 2) Консультація
    if uid in awaiting_consult:
        save_lead(CONSULT_CSV, message.from_user, txt, "consult")
        await notify_admin("запис на консультацію", message.from_user, txt)
        awaiting_consult.discard(uid)
        await message.answer("✅ Заявку на консультацію збережено. Очікуйте підтвердження 🌙", reply_markup=main_keyboard())
        return

    # 3) Навчання
    if uid in awaiting_course:
        save_lead(COURSE_CSV, message.from_user, txt, "learning")
        # Перевірка інстаграм-знижки
        extra = ""
        if "instaznijka".lower() in txt.lower():
            extra = "🌟 Знижка: INSTAZNIJKA"
        await notify_admin("навчання", message.from_user, txt, extra)
        awaiting_course.discard(uid)
        await message.answer("✅ Дякую! Заявку на навчання збережено. Katarsees зв’яжеться з вами 🌙", reply_markup=main_keyboard())
        return

    # Якщо людина пише щось без вибору розділу
    if txt.lower() in {"/start", "start", "/start@Katarsees_bot"}:
        await cmd_start(message)
        return

    await message.answer("Оберіть дію на клавіатурі нижче ⬇️", reply_markup=main_keyboard())

# ==== ТЕСТ ДЛЯ АДМІНА (перевірка ПМ) ====
@dp.message_handler(commands=["test_alert"])
async def test_alert(message: types.Message):
    await notify_admin("Тестове сповіщення", message.from_user, "Це тестове повідомлення.")
    await message.answer("Відправлено тестове сповіщення адмінам.")

# ==== ЗАПУСК ====
import asyncio

if __name__ == "__main__":
    print("✅ Бот запускається…")
    # створюємо і реєструємо подієвий цикл вручну (потрібно для Python 3.11)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    from aiogram.utils import executor
    executor.start_polling(dp, skip_updates=True)
