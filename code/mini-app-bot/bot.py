"""Бот для Mini App «Тесто»: открывает меню кнопкой и принимает заказы из приложения.

Цены пересчитываются на стороне бота по menu.js — подменить сумму из браузера нельзя.
Запуск: заполните .env (BOT_TOKEN, WEBAPP_URL, ADMIN_ID) и выполните  python bot.py
"""
import json
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path

from telegram import KeyboardButton, ReplyKeyboardMarkup, Update, WebAppInfo
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

HERE = Path(__file__).resolve().parent
log = logging.getLogger("testo-bot")


def load_env():
    env = HERE / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def load_menu():
    """Тот же menu.js, что и у приложения, — одна точка правды для цен."""
    text = (HERE / "menu.js").read_text(encoding="utf-8")
    menu = json.loads(text[text.index("["): text.index("];") + 1])
    shop_start = text.index("{", text.index("window.SHOP"))
    shop = json.loads(text[shop_start: text.rindex("}") + 1])
    return {p["id"]: p for p in menu}, shop


load_env()
MENU, SHOP = load_menu()
WEBAPP_URL = os.getenv("WEBAPP_URL", "https://example.com/testo/")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0") or 0)


def rub(n: int) -> str:
    return f"{n:,}".replace(",", " ") + " ₽"


def price_order(order: dict) -> dict:
    """Проверяет заказ и считает сумму заново по ценам бота."""
    lines, goods = [], 0
    for it in order.get("items", []):
        p, q = MENU.get(it.get("id")), int(it.get("q", 0))
        if not p or not 1 <= q <= 50:
            raise ValueError(f"неизвестный товар или количество: {it}")
        goods += p["price"] * q
        lines.append(f"{p['emoji']} {p['name']} × {q} — {rub(p['price'] * q)}")
    if not lines:
        raise ValueError("пустой заказ")
    promo = order.get("promo")
    discount = round(goods * SHOP["promo"][promo] / 100) if promo in SHOP["promo"] else 0
    pickup = order.get("mode") == "pickup"
    delivery = 0 if pickup or goods - discount >= SHOP["freeFrom"] else SHOP["delivery"]
    if goods < SHOP["minOrder"]:
        raise ValueError("сумма меньше минимальной")
    if not pickup and not order.get("addr", "").strip():
        raise ValueError("нет адреса")
    return {"lines": lines, "goods": goods, "discount": discount, "delivery": delivery,
            "total": goods - discount + delivery, "pickup": pickup}


async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    kb = ReplyKeyboardMarkup([[KeyboardButton("🍕 Открыть меню", web_app=WebAppInfo(WEBAPP_URL))]], resize_keyboard=True)
    await update.message.reply_text(
        f"Привет! Это пиццерия <b>«{SHOP['name']}»</b> 🍕\n\nНажмите «Открыть меню» внизу — соберите заказ, "
        "а подтверждение придёт сюда, в чат.", reply_markup=kb, parse_mode=ParseMode.HTML)


async def on_order(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    try:
        order = json.loads(msg.web_app_data.data)
        r = price_order(order)
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as e:
        log.warning("Плохой заказ от %s: %s", update.effective_user.id, e)
        await msg.reply_text("Не получилось оформить заказ 😔 Откройте меню и попробуйте ещё раз.")
        return
    if order.get("total") != r["total"]:
        log.warning("Сумма из приложения %s ≠ сумма бота %s — используем сумму бота", order.get("total"), r["total"])

    num = ctx.bot_data["next_num"] = ctx.bot_data.get("next_num", 1042) + 1
    eta = order.get("time") if order.get("time") not in (None, "asap") else \
        (datetime.now() + timedelta(minutes=40)).strftime("%H:%M")
    where = f"🏃 Самовывоз: {SHOP['pickup']}" if r["pickup"] else f"🚗 Доставка: {order['addr']}"
    money = [f"Товары: {rub(r['goods'])}"]
    if r["discount"]:
        money.append(f"Скидка {order['promo']}: −{rub(r['discount'])}")
    money.append("Доставка: " + (rub(r["delivery"]) if r["delivery"] else "бесплатно"))
    body = "\n".join(r["lines"]) + "\n\n" + "\n".join(money) + f"\n<b>Итого: {rub(r['total'])}</b>\n\n{where}"
    if order.get("note"):
        body += f"\n💬 {order['note']}"

    await msg.reply_text(f"✅ <b>Заказ №{num} принят!</b>\n\n{body}\n\n⏰ {'Будет готов' if r['pickup'] else 'Привезём'} к {eta}",
                         parse_mode=ParseMode.HTML)
    if ADMIN_ID:
        u = update.effective_user
        who = f"@{u.username}" if u.username else u.first_name
        await ctx.bot.send_message(ADMIN_ID, f"🆕 <b>Заказ №{num}</b> от {who}\n\n{body}\n\n⏰ к {eta}", parse_mode=ParseMode.HTML)


def build_app(token: str, request=None) -> Application:
    b = Application.builder().token(token)
    if request:
        b = b.request(request).get_updates_request(request)
    app = b.build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, on_order))
    return app


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise SystemExit("Не задан BOT_TOKEN — скопируйте .env.example в .env и заполните.")
    build_app(token).run_polling(allowed_updates=Update.ALL_TYPES)
