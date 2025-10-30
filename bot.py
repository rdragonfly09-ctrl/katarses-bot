import os
import requests
from fastapi import FastAPI, Request, HTTPException, Header

# ===== ENV =====
BOT_TOKEN = os.environ["BOT_TOKEN"]
BASE_URL = os.environ["BASE_URL"].rstrip("/")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")
ADMIN_ID = os.getenv("ADMIN_ID")  # рядком, напр. "6958130111"

API = f"https://api.telegram.org/bot{BOT_TOKEN}"

app = FastAPI(title="Katarsees Assistant")

# ===== helpers =====
def tg_call(method: str, payload: dict, timeout=15):
    try:
        return requests.post(f"{API}/{method}", json=payload, timeout=timeout)
    except Exception:
        return None

def send_msg(chat_id: int, text: str, kb: dict | None = None):
    data = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if kb:
        data["reply_markup"] = kb
    tg_call("sendMessage", data)

def edit_msg(chat_id: int, message_id: int, text: str, ikb: dict | None = None):
    data = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if ikb:
        data["reply_markup"] = ikb
    tg_call("editMessageText", data)

def answer_cbq(cb_id: str, text: str = "", alert: bool = False):
    tg_call("answerCallbackQuery", {"callback_query_id": cb_id, "text": text, "show_alert": alert})

def set_webhook(url: str) -> bool:
    payload = {"url": url}
    if WEBHOOK_SECRET:
        payload["secret_token"] = WEBHOOK_SECRET
    r = tg_call("setWebhook", payload)
    try:
        return bool(r and r.json().get("ok"))
    except Exception:
        return False

def kb_main():
    return {
        "keyboard": [
            [{"text": "📝 Подати заявку"}],
            [{"text": "🔮 Діагностика (опис)"}],
            [{"text": "🕯 Підтримка"}],
            [{"text": "⬅️ Меню"}],
        ],
        "resize_keyboard": True,
    }

def ikb_lead_controls(user_chat_id: int):
    # у callback_data кодуємо дію та chat_id користувача
    return {
        "inline_keyboard": [[
            {"text": "✅ Прийняти", "callback_data": f"lead|accept|{user_chat_id}"},
            {"text": "❓ Уточнити", "callback_data": f"lead|clarify|{user_chat_id}"},
            {"text": "⛔ Відхилити", "callback_data": f"lead|reject|{user_chat_id}"},
        ]]
    }

# ===== FastAPI lifecycle =====
@app.on_event("startup")
def on_startup():
    wh = f"{BASE_URL}/webhook/{BOT_TOKEN}"
    ok = set_webhook(wh)
    print("Webhook set:" if ok else "Failed to set webhook", wh)

def verify_secret(header_token):
    if not WEBHOOK_SECRET:
        return
    if header_token != WEBHOOK_SECRET:
        raise HTTPException(status_code=401, detail="Invalid secret token")

# ===== handlers =====
@app.post("/webhook/{token}")
async def webhook(token: str, request: Request,
                  x_telegram_bot_api_secret_token: str | None = Header(None)):
    if token != BOT_TOKEN:
        raise HTTPException(status_code=403, detail="Bad token")
    verify_secret(x_telegram_bot_api_secret_token)

    upd = await request.json()

    # --- callback from admin buttons ---
    if "callback_query" in upd:
        cb = upd["callback_query"]
        cb_id = cb["id"]
        from_id = cb["from"]["id"]
        data = cb.get("data", "")

        if not ADMIN_ID or str(from_id) != str(ADMIN_ID):
            answer_cbq(cb_id, "Лише для адміністратора.", alert=True)
            return {"ok": True}

        if data.startswith("lead|"):
            try:
                _, action, user_chat_str = data.split("|")
                user_chat_id = int(user_chat_str)
            except Exception:
                answer_cbq(cb_id, "Некоректні дані.", alert=True)
                return {"ok": True}

            msg = cb.get("message", {})
            admin_chat = msg["chat"]["id"]
            admin_msg_id = msg["message_id"]
            original_text = msg.get("text", "")

            status_map = {
                "accept": "✅ <b>Статус:</b> Прийнято",
                "clarify": "❓ <b>Статус:</b> Уточнити",
                "reject": "⛔ <b>Статус:</b> Відхилено",
            }
            status_line = status_map.get(action, "")

            # 1) оновлюємо адмін-повідомлення (залишимо кнопки або приберемо — на твій смак)
            edit_msg(admin_chat, admin_msg_id, f"{original_text}\n\n{status_line}")

            # 2) повідомляємо користувача
            if action == "accept":
                send_msg(user_chat_id,
                    "Твоя заявка прийнята ✅\n"
                    "Незабаром отримаєш подальші інструкції 🕯")
            elif action == "clarify":
                send_msg(user_chat_id,
                    "Потрібно трохи більше деталей ❓\n"
                    "Будь ласка, відповідай одним повідомленням:\n"
                    "• Суть запиту (1–2 речення)\n"
                    "• Скільки часу це триває?\n"
                    "• Що вже пробувала робити?\n")
            elif action == "reject":
                send_msg(user_chat_id,
                    "Зараз не можу взяти цей запит ⛔\n"
                    "Можеш спробувати сформулювати інакше або звернутись пізніше.")

            answer_cbq(cb_id, "Готово")
        return {"ok": True}

    # --- messages ---
    if "message" in upd:
        msg = upd["message"]
        chat_id = msg["chat"]["id"]
        text = (msg.get("text") or "").strip()
        user = msg.get("from", {})
        username = user.get("username") or "—"
        name = (" ".join([user.get("first_name",""), user.get("last_name","")])).strip() or "—"

        low = text.lower()

        if text.startswith("/start") or low == "⬅️ меню":
            send_msg(chat_id,
                "Вітаю, Душе 🌕\n\n"
                "Я — Асистент <b>Katarsees</b>. Я проведу тебе крізь потік, у якому пробуджується Сила.\n\n"
                "Обери, що тобі потрібно зараз:",
                kb_main()
            )
            return {"ok": True}

        if "подати заявку" in low:
            send_msg(chat_id,
                "Запит прийнято 🌿\n\n"
                "Напиши одним повідомленням:\n"
                "• Ім’я\n"
                "• @нік або посилання на профіль/канал\n"
                "• Що саме потрібно (діагностика / навчання / інше)\n"
                "• Кілька слів — <i>чому відгукнулося саме зараз</i> 💫\n\n"
                "Пиши чесно. Тут тебе чують.",
                kb_main()
            )
            return {"ok": True}

        if "діагностика (опис)" in low:
            send_msg(chat_id,
                "Діагностика — це дзеркало Душі 🕯️\n\n"
                "Через енергію видно, де ти втратила себе, що виснажує, і де схована твоя справжня сила.\n"
                "Хочеш, я поясню коротко, як проходить процес? — напиши «так».",
                kb_main()
            )
            return {"ok": True}

        if "підтримка" in low:
            send_msg(chat_id,
                "Ти не одна 💜\n\n"
                "Напиши, що тебе турбує — і я передам це в потік Katarsees.\n"
                "Навіть якщо просто хочеш виговоритись — це вже початок очищення.",
                kb_main()
            )
            return {"ok": True}

        # Всі інші повідомлення — вважаємо заявкою/зверненням
        if ADMIN_ID:
            admin_text = (
                "📩 <b>Нове звернення</b>\n"
                f"• user: @{username} ({name})\n"
                f"• chat_id: <code>{chat_id}</code>\n"
                f"• text:\n{text}"
            )
            tg_call("sendMessage", {
                "chat_id": int(ADMIN_ID),
                "text": admin_text,
                "parse_mode": "HTML",
                "reply_markup": ikb_lead_controls(chat_id)
            })

        send_msg(chat_id, "Дякую! Заявку/повідомлення надіслано. Очікуй відповіді 🕯", kb_main())

    return {"ok": True}

@app.get("/")
def root():
    return {"status": "ok"}
