# bot.py
# Katarsees Assistant — Render-friendly (без aiogram/aiohttp)
# Працює через FastAPI + вебхук Telegram Bot API.
# Використовує інлайн-кнопки для адміна: Прийняти / Відхилити / Уточнити.
# Автор: для Red Dragonfly 💫

import os
import time
import uuid
import typing as T
import requests
from fastapi import FastAPI, Request, Header, HTTPException
from pydantic import BaseModel

# ──────────────────────────
# ENV
# ──────────────────────────
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
BASE_URL = os.getenv("BASE_URL", "").rstrip("/")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "secret_777")

if not BOT_TOKEN or not ADMIN_ID or not BASE_URL:
    raise RuntimeError("BOT_TOKEN / ADMIN_ID / BASE_URL must be set in Environment.")

API = f"https://api.telegram.org/bot{BOT_TOKEN}"

# ──────────────────────────
# FastAPI
# ──────────────────────────
app = FastAPI(title="Katarsees Assistant")

# ──────────────────────────
# МІНІ-ПАМ’ЯТЬ (стейт користувача)
# зберігаємо коротко що чекаємо від користувача після натискання кнопки
# { user_id: {"state": "...", "ts": <time>} }
# ──────────────────────────
STATE: dict[int, dict] = {}

def set_state(user_id: int, state: str | None):
    if state is None:
        STATE.pop(user_id, None)
    else:
        STATE[user_id] = {"state": state, "ts": time.time()}

def get_state(user_id: int) -> str | None:
    rec = STATE.get(user_id)
    # чистимо старі стейти > 2 год
    if rec and (time.time() - rec.get("ts", 0) > 2*60*60):
        STATE.pop(user_id, None)
        return None
    return rec["state"] if rec else None

# ──────────────────────────
# Допоміжні: відправка в TG
# ──────────────────────────
def tg(method: str, payload: dict) -> dict:
    r = requests.post(f"{API}/{method}", json=payload, timeout=15)
    if r.status_code != 200:
        raise RuntimeError(f"TG error {r.status_code}: {r.text}")
    data = r.json()
    if not data.get("ok"):
        raise RuntimeError(f"TG not ok: {data}")
    return data["result"]

def send_message(chat_id: int, text: str, reply_markup: dict | None = None, parse_mode: str = "HTML"):
    return tg("sendMessage", {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True,
        "reply_markup": reply_markup or {}
    })

def answer_callback_query(callback_query_id: str, text: str = "", show_alert: bool = False):
    tg("answerCallbackQuery", {
        "callback_query_id": callback_query_id,
        "text": text,
        "show_alert": show_alert
    })

def edit_message_reply_markup(chat_id: int, message_id: int, reply_markup: dict | None = None):
    tg("editMessageReplyMarkup", {
        "chat_id": chat_id,
        "message_id": message_id,
        "reply_markup": reply_markup or {}
    })

# ──────────────────────────
# Клавіатури
# ──────────────────────────
def main_menu_kbd() -> dict:
    # звичайна ReplyKeyboardMarkup
    return {
        "keyboard": [
            [{"text": "🗓️ Запис на консультацію"}],
            [{"text": "🔮 Діагностика"}],
            [{"text": "📚 Навчання"}],
            [{"text": "💰 Оплата"}],
            [{"text": "⬅️ Назад"}],
        ],
        "resize_keyboard": True,
        "one_time_keyboard": False
    }

def admin_decision_kbd(uid: int) -> dict:
    # інлайн для адміна
    return {
        "inline_keyboard": [[
            {"text": "✅ Прийняти", "callback_data": f"appr:{uid}:{uuid.uuid4().hex[:6]}"},
            {"text": "❌ Відхилити", "callback_data": f"decl:{uid}:{uuid.uuid4().hex[:6]}"},
            {"text": "❓ Уточнити", "callback_data": f"ask:{uid}:{uuid.uuid4().hex[:6]}"},
        ]]
    }

# ──────────────────────────
# Тексти-відповіді (можеш правити сміливо)
# ──────────────────────────
WELCOME = (
    "Вітаю, я <b>Katarsees Assistant</b> ✨\n"
    "Обери розділ нижче або просто напиши свій запит.\n"
    "Я передам його Katarsees і ми повернемося з відповіддю 🕯"
)

TXT_ZAPYS = (
    "🗓️ <b>Запис на консультацію</b>\n\n"
    "Вкажи формат (онлайн/очно), зручний часовий пояс, своє ім’я + @username або телефон. "
    "Katarsees зв’яжеться з тобою найближчим часом 🌗"
)

TXT_DIAG = (
    "🔮 <b>Діагностика</b>\n\n"
    "Напиши коротко, що болить: енергія, любов, шлях, фінанси, родові теми. "
    "Katarsees бачить глибше, ніж здається 👁‍🕯"
)

TXT_NAVCH = (
    "📚 <b>Навчання</b>\n\n"
    "Хочеш повний курс чи пробний урок? Напиши рівень підготовки та ціль. "
    "Katarsees підкаже, з чого краще стартувати 🔥"
)

TXT_OPLATA = (
    "💰 <b>Оплата</b>\n\n"
    "Оплата — це енергетичний договір. Реквізити надішлемо після підтвердження твого запиту 🪶"
)

TXT_BACK = "Повертаємось у головне меню ⤴️"

TXT_SENT = "Дякую! Заявку/повідомлення надіслано. Очікуй відповіді від Katarsees 🕯"

# ──────────────────────────
# Встановлення вебхука при старті
# ──────────────────────────
def set_webhook():
    url = f"{BASE_URL}/webhook"
    # Секретний токен — обов’язково!
    tg("setWebhook", {
        "url": url,
        "allowed_updates": ["message", "callback_query"],
        "secret_token": WEBHOOK_SECRET,
        # на Render без self-signed сертифікатів — тому нічого додатково не шлемо
        "drop_pending_updates": True
    })

@app.on_event("startup")
def on_startup():
    set_webhook()

# ──────────────────────────
# Моделі апдейту (мінімальні)
# ──────────────────────────
class From(BaseModel):
    id: int
    first_name: str | None = None
    username: str | None = None

class Chat(BaseModel):
    id: int
    type: str

class Message(BaseModel):
    message_id: int
    chat: Chat
    text: str | None = None
    from_: From | None = None

    class Config:
        fields = {"from_": "from"}

class CallbackQuery(BaseModel):
    id: str
    from_: From
    message: Message
    data: str

    class Config:
        fields = {"from_": "from"}

class Update(BaseModel):
    update_id: int
    message: Message | None = None
    callback_query: CallbackQuery | None = None

# ──────────────────────────
# Логіка
# ──────────────────────────
def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID

def forward_application_to_admin(
    user_id: int, first_name: str, username: str | None, text: str, kind: str
):
    uname = f"@{username}" if username else "—"
    msg = (
        f"🔔 <b>Нова заявка ({kind})</b>!\n"
        f"🧿 Ім’я: {first_name or '—'}\n"
        f"🪪 ID: <code>{user_id}</code>\n"
        f"📢 Користувач: {first_name or '—'}, {uname}\n"
        f"✍️ Текст: {text}"
    )
    send_message(ADMIN_ID, msg, reply_markup=admin_decision_kbd(user_id))

def handle_text(user: From, chat_id: int, text: str):
    t = (text or "").strip()

    # меню
    if t in ("/start", "⬅️ Назад"):
        send_message(chat_id, WELCOME, reply_markup=main_menu_kbd())
        set_state(user.id, None)
        return

    # кнопки верхнього рівня
    if t == "🗓️ Запис на консультацію":
        send_message(chat_id, TXT_ZAPYS, reply_markup=main_menu_kbd())
        set_state(user.id, "ZAPYS")
        return
    if t == "🔮 Діагностика":
        send_message(chat_id, TXT_DIAG, reply_markup=main_menu_kbd())
        set_state(user.id, "DIAG")
        return
    if t == "📚 Навчання":
        send_message(chat_id, TXT_NAVCH, reply_markup=main_menu_kbd())
        set_state(user.id, "NAVCH")
        return
    if t == "💰 Оплата":
        send_message(chat_id, TXT_OPLATA, reply_markup=main_menu_kbd())
        set_state(user.id, None)
        return

    # якщо користувач у стані — трактуємо як заявку
    state = get_state(user.id)
    if state in ("ZAPYS", "DIAG", "NAVCH"):
        kind = {"ZAPYS": "консультація", "DIAG": "діагностика", "NAVCH": "навчання"}[state]
        forward_application_to_admin(user.id, user.first_name or "", user.username, t, kind)
        send_message(chat_id, TXT_SENT, reply_markup=main_menu_kbd())
        set_state(user.id, None)
        return

    # дефолт — просто перекидаємо як повідомлення/заявку
    forward_application_to_admin(user.id, user.first_name or "", user.username, t, "повідомлення")
    send_message(chat_id, TXT_SENT, reply_markup=main_menu_kbd())

# ──────────────────────────
# Обробка колбеків адміна
# callback_data формат: "<verb>:<user_id>:<nonce>"
# ──────────────────────────
def handle_admin_callback(cb: CallbackQuery):
    if not is_admin(cb.from_.id):
        answer_callback_query(cb.id, "Лише для адміністратора.", True)
        return

    try:
        verb, uid_str, _ = cb.data.split(":", 2)
        target = int(uid_str)
    except Exception:
        answer_callback_query(cb.id, "Некоректні дані.", True)
        return

    if verb == "appr":
        # Прийняти
        send_message(target,
            "✅ <b>Запит підтверджено</b>.\n"
            "Katarsees скоро надішле подальші кроки або реквізити 🕯",
            reply_markup=main_menu_kbd())
        answer_callback_query(cb.id, "Підтверджено.")
        # (опц) прибрати кнопки під адмін-повідомленням
        edit_message_reply_markup(cb.message.chat.id, cb.message.message_id, {})
        return

    if verb == "decl":
        # Відхилити
        send_message(target,
            "❌ <b>Запит відхилено</b>.\n"
            "Якщо хочеш — надішли новий запит з уточненнями 💫",
            reply_markup=main_menu_kbd())
        answer_callback_query(cb.id, "Відхилено.")
        edit_message_reply_markup(cb.message.chat.id, cb.message.message_id, {})
        return

    if verb == "ask":
        # Запросити уточнення
        send_message(target,
            "❓ <b>Потрібні уточнення</b>.\n"
            "Напиши, будь ласка: тема/ціль + що саме очікуєш від результату. "
            "Після відповіді я передам повідомлення Katarsees 🕯",
            reply_markup=main_menu_kbd())
        answer_callback_query(cb.id, "Надіслано прохання уточнити.")
        edit_message_reply_markup(cb.message.chat.id, cb.message.message_id, {})
        return

    answer_callback_query(cb.id, "Невідомо.")

# ──────────────────────────
# Вебхук
# ──────────────────────────
@app.post("/webhook")
async def webhook(req: Request, x_telegram_bot_api_secret_token: str = Header(None)):
    # Перевіряємо секрет
    if x_telegram_bot_api_secret_token != WEBHOOK_SECRET:
        raise HTTPException(status_code=401, detail="Bad secret")

    data = await req.json()
    upd = Update(**data)

    if upd.message and upd.message.text is not None:
        m = upd.message
        frm = m.from_
        if frm is None:
            return {"ok": True}
        handle_text(frm, m.chat.id, m.text)
        return {"ok": True}

    if upd.callback_query:
        handle_admin_callback(upd.callback_query)
        return {"ok": True}

    return {"ok": True}

# ──────────────────────────
# Healthcheck (опційно)
# ──────────────────────────
@app.get("/")
def root():
    return {"ok": True, "bot": "Katarsees Assistant"}
