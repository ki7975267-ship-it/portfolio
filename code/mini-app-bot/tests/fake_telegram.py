"""Имитация сервера Telegram: бот работает по-настоящему, но без интернета и без токена.
Записывает все сообщения, чтобы тест мог проверить, что увидел бы пользователь."""
import copy
import itertools
import json
import time
from collections import defaultdict

from telegram import Update
from telegram.request import BaseRequest

BOT_USER = {"id": 100, "is_bot": True, "first_name": "Щетина", "username": "shchetina_demo_bot"}


class FakeTelegram(BaseRequest):
    def __init__(self):
        self.ids = itertools.count(1000)
        self.chats = defaultdict(list)          # chat_id -> сообщения в порядке появления
        self.keyboard = {}                      # chat_id -> текущая клавиатура внизу экрана
        self.toasts = []                        # всплывающие ответы на нажатия
        self.snaps = []

    @property
    def read_timeout(self):
        return 5.0

    async def initialize(self):
        pass

    async def shutdown(self):
        pass

    async def do_request(self, url, method, request_data=None, *args, **kwargs):
        name = url.rsplit("/", 1)[-1]
        p = request_data.parameters if request_data else {}
        result = True
        if name == "getMe":
            result = BOT_USER
        elif name == "sendMessage":
            chat = int(p["chat_id"])
            msg = {"id": next(self.ids), "from": "bot", "text": p["text"], **self._markup(chat, p)}
            self.chats[chat].append(msg)
            result = self._json(chat, msg)
        elif name == "editMessageText":
            chat = int(p["chat_id"])
            msg = next(m for m in self.chats[chat] if m["id"] == int(p["message_id"]))
            msg.update({"text": p["text"], "inline": None, "_data": None, **self._markup(chat, p)})
            msg.pop("pressed", None)
            result = self._json(chat, msg)
        elif name == "answerCallbackQuery":
            if p.get("text"):
                self.toasts.append(p["text"])
        return 200, json.dumps({"ok": True, "result": result}).encode()

    def _markup(self, chat, p):
        m = p.get("reply_markup") or {}
        if isinstance(m, str):
            m = json.loads(m)
        if "inline_keyboard" in m:
            return {"inline": [[b["text"] if isinstance(b, dict) else b for b in row] for row in m["inline_keyboard"]],
                    "_data": [[b.get("callback_data") for b in row] for row in m["inline_keyboard"]]}
        if "keyboard" in m:
            self.keyboard[chat] = [[b["text"] if isinstance(b, dict) else b for b in row] for row in m["keyboard"]]
        return {}

    @staticmethod
    def _json(chat, msg):
        return {"message_id": msg["id"], "date": int(time.time()), "chat": {"id": chat, "type": "private"},
                "from": BOT_USER, "text": msg["text"]}

    # --- действия пользователя ---

    def user(self, uid, first_name):
        return {"id": uid, "is_bot": False, "first_name": first_name, "language_code": "ru"}

    def text_update(self, bot, uid, first_name, text, contact=None):
        mid = next(self.ids)
        self.chats[uid].append({"id": mid, "from": "user", "text": text if not contact else "📱 " + contact})
        msg = {"message_id": mid, "date": int(time.time()), "chat": {"id": uid, "type": "private"},
               "from": self.user(uid, first_name)}
        if contact:
            msg["contact"] = {"phone_number": contact, "first_name": first_name, "user_id": uid}
        else:
            msg["text"] = text
            if text.startswith("/"):
                msg["entities"] = [{"type": "bot_command", "offset": 0, "length": len(text.split()[0])}]
        return Update.de_json({"update_id": mid, "message": msg}, bot)

    def press_update(self, bot, uid, first_name, button_text):
        """Нажать кнопку под последним сообщением бота, где она есть (по тексту на кнопке)."""
        for msg in reversed(self.chats[uid]):
            for r, row in enumerate(msg.get("inline") or []):
                if button_text in row:
                    data = msg["_data"][r][row.index(button_text)]
                    msg["pressed"] = button_text
                    q = {"id": str(next(self.ids)), "from": self.user(uid, first_name), "chat_instance": "1",
                         "data": data, "message": {"message_id": msg["id"], "date": int(time.time()),
                                                   "chat": {"id": uid, "type": "private"}, "from": BOT_USER,
                                                   "text": msg["text"]}}
                    return Update.de_json({"update_id": next(self.ids), "callback_query": q}, bot)
        raise AssertionError(f"Кнопка «{button_text}» не найдена. Последнее сообщение: {self.last(uid)}")

    def last(self, chat):
        return self.chats[chat][-1]

    def snapshot(self, chat, label):
        self.snaps.append({"label": label, "chat": chat, "messages": copy.deepcopy(self.chats[chat]),
                           "keyboard": copy.deepcopy(self.keyboard.get(chat))})
