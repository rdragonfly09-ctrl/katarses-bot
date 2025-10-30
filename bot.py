import os
import time
import threading
import requests
from typing import Dict, Any, Optional, List
from fastapi import FastAPI
from fastapi.responses import PlainTextResponse

# ========= CONFIG =========
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_ID = int(os.getenv("ADMIN_ID", "0").strip() or "0")
BASE_URL = os.getenv("BASE_URL", "").strip()  # не обов'язково; просто для /health
TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

if not BOT_TOKEN or not ADMIN_ID:
    raise RuntimeError("Set env vars BOT_TOKEN and ADMIN_ID")

# ========= APP =========
app = FastAPI()

# ========= STATE (in-memory) =========
last_update_id = 0
user_states: Dict[int, str] = {}        # chat_id -> "lead_name_wait" / "lead_text_wait" / "" ...
user_leads: Dict[int, Dict[str, Any]] = {}  # тимчасове збереження заявки користувача

# ========= COMMON =========
def tg_call(method: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    url = f"{TELEGRAM_API}/{method}"
    r = requests.post(url, json=payload, timeout=30)
    try:
        return r.json()
    except Exception:
        return {"ok": False, "error": r.text}

def send_msg(chat_id: int, text: str, kb: Optional[Dict] = None, parse: str = "HTML"):
    payload = {"chat_id": chat_id, "text": text, "parse_mode": parse}
    if kb:
        payload["reply_markup"] = kb
    return tg_call("sendMessage", payload)

def edit_msg(chat_id: int, msg_id: int, text: str, kb: Optional[Dict] = None, parse: str = "HTML"):
    payload = {"chat_id": chat_id, "message_id": msg_id, "text": text, "parse_mode": parse}
    if kb:
        payload["reply_markup"] = kb
    return tg_call("editMessageText", payload)

def answer_cb(cb_id: str, text: str = "", alert: bool = False):
    return tg_call("answerCallbackQuery", {"callback_query_id": cb_id, "text": text, "show_alert": alert})

# ========= KEYBOARDS =========
def reply_menu():
    return {
        "keyboard": [
            [{"text": "📝 Подати заявку"}],
            [{"text": "🔮 Діагностика (опис)"}],
            [{"text": "🕯 Підтримка"}],
            [{"text": "⬅️ Меню"}],
        ],
        "resize_keyboard": True,
        "one_time_keyboard": False
    }

def ikb_lead_controls(user_chat_id: int):
    return {
        "inline_keyboard": [[
            {"text": "✅ Прийняти", "callback_data": f"lead|accept|{user_chat_id}"},
            {"text": "❓ Уточнити", "callback_data": f"lead|clarify|{user_chat_id}"},
            {"text": "⛔ Відхилити", "callback_data": f"lead|reject|{user_chat_id}"},
        ]]
    }

# ========= TEMPLATES =========
WELCOME = (
    "Вітаю! Я асистент. Надішли мені будь-який текст — я відповім.\n"
    "Щоб змінити текст — просто напиши нове повідомлення."
)
HINT_APPLY = (
    "📝 <b>Подати заявку</b>\n\n"
    "Напиши одним повідомленням:\n"
    "• Ім’я\n"
    "• @нік або посилання на профіль/канал\n"
    "• Що потрібно (діагностика/навчання/інше)\n"
    "• Короткий опис запиту.\n\n"
    "Після надсилання я передам заявку та повернусь із відповіддю."
)
HINT_DIAG = (
    "🔮 <b>Діагностика (опис)</b>\n\n"
    "Напиши коротко <i>що саме болить</i> і <i>чого хочеш досягти</i>.\n"
    "Приклади:\n"
    "• «Постійна втома, провали в енергії — хочу зрозуміти причину»\n"
    "• «Стосунки з чоловіком застигли — що блокує?»\n"
    "• «Гроші йдуть, не затримуються — де дірка?»"
)
HINT_SUPPORT = (
    "🕯 <b>Підтримка</b>\n\n"
    "Можеш написати питання — і я підкажу, куди натиснути. "
    "Якщо щось термінове — кинь опис, я позначу пріоритетно."
)
AFTER_SENT = "Дякую! Заявку/повідомлення надіслано. Очікуйте відповіді 🕯"

# ========= ADMIN TEMPLATES =========
def admin_lead_text(user_id: int, name: str, username: str, text: str) -> str:
    uu = f"@{username}" if username else "—"
    return (
        "🔔 <b>Нова заявка (діагностика)</b>!\n"
        f"🧑‍💼 <b>Ім’я:</b> {name}\n"
        f"🪪 <b>ID:</b> {user_id}\n"
        f"📢 <b>Користувач:</b> {uu}\n"
        f"✍️ <b>Текст:</b> {text}"
    )

ACCEPT_MSG = (
    "✅ <b>Заявка прийнята.</b>\n"
    "Ми на зв’язку. Протягом доби надамо деталі щодо діагностики/навчання 🕯"
)
REJECT_MSG = (
    "⛔ <b>Заявка відхилена.</b>\n"
    "На жаль, зараз ми не можемо взяти запит. Спробуй пізніше або уточни деталі."
)
CLARIFY_MSG = (
    "❓ <b>Уточнення</b>\n"
    "Напиши, будь ласка, трохи детальніше: коли почалося, які відчуття/ситуації, "
    "чи були події напередодні."
)

# ========= LOGIC =========
def reset_user(chat_id: int):
    user_states.pop(chat_id, None)
    user_leads.pop(chat_id, None)

def handle_text(chat_id: int, text: str, from_user: Dict[str, Any]):
    t = text.strip()

    # універсальне меню
    if t in ("/start", "⬅️ Меню", "Меню"):
        reset_user(chat_id)
        send_msg(chat_id, WELCOME, reply_menu())
        return

    # стартові кнопки
    if t.startswith("📝"):
        reset_user(chat_id)
        user_states[chat_id] = "lead_wait_all_fields"
        send_msg(chat_id, HINT_APPLY, reply_menu())
        return

    if t.startswith("🔮"):
        reset_user(chat_id)
        user_states[chat_id] = "diag_wait_text"
        send_msg(chat_id, HINT_DIAG, reply_menu())
        return

    if t.startswith("🕯"):
        reset_user(chat_id)
        send_msg(chat_id, HINT_SUPPORT, reply_menu())
        return

    # якщо чекаємо заявку одним повідомленням
    st = user_states.get(chat_id, "")
    if st == "lead_wait_all_fields":
        name = (from_user.get("first_name") or "").strip() or "—"
        username = from_user.get("username") or ""
        user_leads[chat_id] = {"name": name, "username": username, "text": t}
        # повідомити адміна
        admin_text = admin_lead_text(chat_id, name, username, t)
        send_msg(ADMIN_ID, admin_text, ikb_lead_controls(chat_id))
        send_msg(chat_id, AFTER_SENT, reply_menu())
        reset_user(chat_id)
        return

    if st == "diag_wait_text":
        name = (from_user.get("first_name") or "").strip() or "—"
        username = from_user.get("username") or ""
        user_leads[chat_id] = {"name": name, "username": username, "text": f"[ДІАГНОСТИКА] {t}"}
        admin_text = admin_lead_text(chat_id, name, username, f"[ДІАГНОСТИКА] {t}")
        send_msg(ADMIN_ID, admin_text, ikb_lead_controls(chat_id))
        send_msg(chat_id, AFTER_SENT, reply_menu())
        reset_user(chat_id)
        return

    # дефолт: просто повертаємо меню + легка відповідь
    send_msg(chat_id, "Я працюю на Render без aiohttp 😉\nОбери дію нижче.", reply_menu())

def handle_callback(cb: Dict[str, Any]):
    data = cb.get("data") or ""
    cb_id = cb.get("id")
    msg = cb.get("message", {})
    m_chat_id = msg.get("chat", {}).get("id")
    m_id = msg.get("message_id")

    parts = data.split("|")
    if len(parts) != 3 or parts[0] != "lead":
        answer_cb(cb_id)
        return

    action, user_chat_id_s = parts[1], parts[2]
    try:
        user_chat_id = int(user_chat_id_s)
    except:
        answer_cb(cb_id, "Помилка формату", True)
        return

    # оновлюємо адмін-повідомлення + пишемо користувачу
    if action == "accept":
        edit_msg(m_chat_id, m_id, msg.get("text", "") + "\n\n✅ <b>Статус:</b> прийнято.")
        send_msg(user_chat_id, ACCEPT_MSG, reply_menu())
        answer_cb(cb_id, "Прийнято")
    elif action == "clarify":
        edit_msg(m_chat_id, m_id, msg.get("text", "") + "\n\n❓ <b>Статус:</b> запитано уточнення.")
        send_msg(user_chat_id, CLARIFY_MSG, reply_menu())
        answer_cb(cb_id, "Запитано уточнення")
    elif action == "reject":
        edit_msg(m_chat_id, m_id, msg.get("text", "") + "\n\n⛔ <b>Статус:</b> відхилено.")
        send_msg(user_chat_id, REJECT_MSG, reply_menu())
        answer_cb(cb_id, "Відхилено")
    else:
        answer_cb(cb_id)

# ========= POLLING =========
def poller():
    global last_update_id
    # легке підсвідоме "warming up"
    time.sleep(2)
    while True:
        try:
            params = {"timeout": 25, "allowed_updates": ["message", "callback_query"]}
            if last_update_id:
                params["offset"] = last_update_id + 1
            r = requests.get(f"{TELEGRAM_API}/getUpdates", params=params, timeout=30)
            data = r.json()
            if not data.get("ok"):
                time.sleep(2)
                continue

            for upd in data.get("result", []):
                last_update_id = upd["update_id"]

                # callback
                if "callback_query" in upd:
                    handle_callback(upd["callback_query"])
                    continue

                # messages
                msg = upd.get("message")
                if not msg:
                    continue
                chat_id = msg["chat"]["id"]
                text = msg.get("text", "") or ""
                from_user = msg.get("from", {}) or {}
                handle_text(chat_id, text, from_user)

        except Exception as e:
            # тиха пауза та повтор
            time.sleep(2)

# ========= FASTAPI ROUTES =========
@app.get("/", response_class=PlainTextResponse)
def root():
    return "OK"

@app.get("/health", response_class=PlainTextResponse)
def health():
    return "healthy"

# запускаємо поллер у фоні
def _run_poller_bg_once():
    th = threading.Thread(target=poller, daemon=True)
    th.start()

_run_poller_bg_once()
