"""Telegram-бот онлайн-записи в барбершоп.

Запуск:  python bot.py   (перед этим заполните .env — см. README.md)
"""
import logging
from datetime import date, datetime, timedelta

from telegram import (InlineKeyboardButton as IB, InlineKeyboardMarkup, KeyboardButton,
                      ReplyKeyboardMarkup, Update)
from telegram.constants import ParseMode
from telegram.ext import (Application, CallbackQueryHandler, CommandHandler, ContextTypes,
                          MessageHandler, filters)

import config
from data import (ADDRESS, DAYS_AHEAD, HOURS, MASTERS, SALON, SERVICES, day_label, day_title,
                  free_slots, long_date, rub)
from db import DB

log = logging.getLogger("barber-bot")

BTN_BOOK, BTN_MY, BTN_PRICE, BTN_ROUTE = "✂️ Записаться", "📅 Мои записи", "💈 Услуги и цены", "📍 Как добраться"
MAIN_MENU = ReplyKeyboardMarkup([[BTN_BOOK], [BTN_MY, BTN_PRICE], [BTN_ROUTE]], resize_keyboard=True)
CANCEL_WORD = "Отмена"


def now() -> datetime:
    """Текущее время салона (без часового пояса). В тестах подменяется."""
    return datetime.now(config.TZ).replace(tzinfo=None)


def kb(*rows) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([list(r) for r in rows])


def chunks(items, n):
    return [items[i:i + n] for i in range(0, len(items), n)]


def db_of(ctx: ContextTypes.DEFAULT_TYPE) -> DB:
    return ctx.application.bot_data["db"]


def draft(ctx) -> dict:
    return ctx.user_data.setdefault("draft", {})


def master_name(mid: str) -> str:
    return MASTERS[mid].name if mid in MASTERS else "любой мастер"


# ---------- расчёт свободного времени ----------

def slots_for(ctx, day: date, master: str, minutes: int) -> list[datetime]:
    db, t = db_of(ctx), now()
    ids = MASTERS if master == "any" else [master]
    found = set()
    for mid in ids:
        found.update(free_slots(day, minutes, db.busy(mid, day), t))
    return sorted(found)


def pick_master(ctx, start: datetime, master: str, minutes: int) -> str | None:
    """Проверяет, что время ещё свободно, и выбирает мастера для «любого»."""
    for mid in (MASTERS if master == "any" else [master]):
        if start in free_slots(start.date(), minutes, db_of(ctx).busy(mid, start.date()), now()):
            return mid
    return None


# ---------- экраны (текст + кнопки) ----------

def scr_services():
    rows = [[IB(f"{s.title} · {rub(s.price)}", callback_data=f"svc:{s.id}")] for s in SERVICES.values()]
    return "<b>Выберите услугу</b>", InlineKeyboardMarkup(rows + [[IB("Отмена", callback_data="x")]])


def scr_masters(d):
    s = SERVICES[d["svc"]]
    rows = [[IB("Любой свободный мастер", callback_data="mst:any")]]
    rows += [[IB(f"{m.name} — {m.about}", callback_data=f"mst:{m.id}")] for m in MASTERS.values()]
    rows += [[IB("← Назад", callback_data="bk:svc")]]
    return f"<b>{s.title}</b> · {s.minutes} мин · {rub(s.price)}\n\nК кому записать?", InlineKeyboardMarkup(rows)


def scr_days(ctx, d):
    s, today = SERVICES[d["svc"]], now().date()
    days = [today + timedelta(days=i) for i in range(DAYS_AHEAD)]
    days = [x for x in days if slots_for(ctx, x, d["mst"], s.minutes)]
    if not days:
        return ("На ближайшую неделю всё занято 😔\nПопробуйте выбрать другого мастера.",
                kb([IB("← Выбрать мастера", callback_data="bk:mst")]))
    btns = [IB(day_label(x, today), callback_data=f"day:{x.isoformat()}") for x in days]
    text = f"<b>{s.title}</b> · {master_name(d['mst'])}\n\nВыберите день:"
    return text, InlineKeyboardMarkup(chunks(btns, 4) + [[IB("← Назад", callback_data="bk:mst")]])


def scr_times(ctx, d):
    s, day = SERVICES[d["svc"]], date.fromisoformat(d["day"])
    slots = slots_for(ctx, day, d["mst"], s.minutes)
    if not slots:
        return "Это время только что заняли. Выберите другой день:", kb([IB("← К выбору дня", callback_data="bk:day")])
    btns = [IB(f"{t:%H:%M}", callback_data=f"tm:{t:%H%M}") for t in slots]
    text = (f"<b>{s.title}</b> · {master_name(d['mst'])}\n"
            f"📅 {day_title(day, now().date())}\n\nСвободное время:")
    return text, InlineKeyboardMarkup(chunks(btns, 4) + [[IB("← Другой день", callback_data="bk:day")]])


def summary(d, title):
    s, start = SERVICES[d["svc"]], datetime.fromisoformat(d["start"])
    return (f"{title}\n\n"
            f"✂️ {s.title} — {rub(s.price)}\n"
            f"👤 Мастер: {master_name(d['mst'])}\n"
            f"📅 {long_date(start)}\n"
            f"⏱ {s.minutes} минут\n\n"
            f"🙋 {d['name']}, {d['phone']}")


def scr_confirm(d):
    return summary(d, "<b>Проверьте запись</b>"), kb(
        [IB("✅ Подтвердить", callback_data="ok")],
        [IB("🕒 Другое время", callback_data="bk:day"), IB("Отмена", callback_data="x")])


def format_phone(raw: str) -> str | None:
    digits = "".join(ch for ch in raw if ch.isdigit())
    if len(digits) == 11 and digits[0] in "78":
        digits = digits[1:]
    if len(digits) != 10:
        return None
    return f"+7 ({digits[:3]}) {digits[3:6]}-{digits[6:8]}-{digits[8:]}"


# ---------- команды и меню ----------

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data.clear()
    name = update.effective_user.first_name or "друг"
    await update.message.reply_text(
        f"Привет, {name}! 👋\n\nЭто бот <b>{SALON}</b>. Здесь можно за минуту записаться к мастеру, "
        "посмотреть свои записи и цены.\n\nВыберите, что нужно 👇",
        reply_markup=MAIN_MENU, parse_mode=ParseMode.HTML)


async def book(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["draft"] = {}
    ctx.user_data.pop("wait", None)
    text, markup = scr_services()
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=markup, parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text(text, reply_markup=markup, parse_mode=ParseMode.HTML)


async def my_bookings(update: Update, ctx: ContextTypes.DEFAULT_TYPE, note: str = ""):
    rows = db_of(ctx).upcoming(update.effective_user.id, now())
    if not rows:
        text, markup = (note + "У вас пока нет записей."), kb([IB(BTN_BOOK, callback_data="go:book")])
    else:
        lines = [note + "<b>Ваши записи</b>"]
        btns = []
        for r in rows:
            start = datetime.fromisoformat(r["start"])
            lines.append(f"\n📅 {long_date(start)}\n✂️ {SERVICES[r['service']].title} · {master_name(r['master'])}")
            btns.append([IB(f"❌ Отменить {start:%d.%m} в {start:%H:%M}", callback_data=f"cx:{r['id']}")])
        text, markup = "\n".join(lines), InlineKeyboardMarkup(btns)
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=markup, parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text(text, reply_markup=markup, parse_mode=ParseMode.HTML)


async def prices(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    lines = ["<b>Услуги и цены</b>\n"]
    lines += [f"✂️ {s.title} — <b>{rub(s.price)}</b> · {s.minutes} мин" for s in SERVICES.values()]
    lines += ["\nМастера: " + ", ".join(m.name for m in MASTERS.values())]
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML,
                                    reply_markup=kb([IB(BTN_BOOK, callback_data="go:book")]))


async def route(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"<b>{SALON}</b>\n\n📍 {ADDRESS}\n🕙 {HOURS}", parse_mode=ParseMode.HTML)


async def today(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """/today — записи на сегодня (только для администратора)."""
    if update.effective_user.id != config.ADMIN_ID:
        return
    rows = db_of(ctx).on_day(now().date())
    if not rows:
        await update.message.reply_text("Сегодня записей нет.")
        return
    lines = [f"<b>Записи на сегодня — {len(rows)}</b>\n"]
    for r in rows:
        t = datetime.fromisoformat(r["start"])
        lines.append(f"{t:%H:%M} · {master_name(r['master'])} · {SERVICES[r['service']].title}\n"
                     f"      {r['name']}, {r['phone']}")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


# ---------- кнопки под сообщениями ----------

# какие ответы уже должны быть в черновике, чтобы кнопка имела смысл
NEEDS = {"mst": ["svc"], "day": ["svc", "mst"], "tm": ["svc", "mst", "day"], "me": ["svc", "mst", "start"],
         "ok": ["svc", "mst", "start", "name", "phone"], "bk:mst": ["svc"], "bk:day": ["svc", "mst"]}


async def on_button(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q, d = update.callback_query, draft(ctx)
    key, _, val = q.data.partition(":")

    if key == "cx":
        return await cancel_booking(update, ctx, int(val))
    if key == "x":
        ctx.user_data.clear()
        await q.answer("Запись отменена")
        return await q.edit_message_text("Хорошо, не записываем. Возвращайтесь, когда будет удобно! 👋")
    await q.answer()

    if key == "go" or q.data == "bk:svc":
        return await book(update, ctx)
    need = NEEDS.get(q.data if key == "bk" else key, []) + (["known"] if q.data == "me:yes" else [])
    if any(k not in d for k in need):
        return await q.edit_message_text("Эта кнопка устарела — давайте начнём заново.",
                                         reply_markup=kb([IB(BTN_BOOK, callback_data="go:book")]))

    if q.data == "bk:mst":
        text, markup = scr_masters(d)
    elif q.data == "bk:day":
        text, markup = scr_days(ctx, d)
    elif key == "svc":
        d["svc"] = val
        text, markup = scr_masters(d)
    elif key == "mst":
        d["mst"] = val
        text, markup = scr_days(ctx, d)
    elif key == "day":
        d["day"] = val
        text, markup = scr_times(ctx, d)
    elif key == "tm":
        d["start"] = datetime.combine(date.fromisoformat(d["day"]),
                                      datetime.strptime(val, "%H%M").time()).isoformat(timespec="minutes")
        known = db_of(ctx).last_contact(update.effective_user.id)
        if known:
            d["known"] = dict(known)
            text = f"Записать на имя <b>{known['name']}</b>, {known['phone']}?"
            markup = kb([IB("Да, это я", callback_data="me:yes")], [IB("Указать другие данные", callback_data="me:no")])
        else:
            ctx.user_data["wait"] = "name"
            text, markup = "Как вас зовут?", None
    elif key == "me":
        if val == "yes":
            d.update(d.pop("known"))
            text, markup = scr_confirm(d)
        else:
            ctx.user_data["wait"] = "name"
            text, markup = "Как вас зовут?", None
    elif key == "ok":
        return await confirm(update, ctx)
    else:
        return
    await q.edit_message_text(text, reply_markup=markup, parse_mode=ParseMode.HTML)


async def confirm(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q, d = update.callback_query, draft(ctx)
    s, start = SERVICES[d["svc"]], datetime.fromisoformat(d["start"])
    mid = pick_master(ctx, start, d["mst"], s.minutes)
    if not mid:
        d.pop("start", None)
        text, markup = scr_times(ctx, d)
        return await q.edit_message_text("😔 Это время только что заняли.\n\n" + text, reply_markup=markup,
                                         parse_mode=ParseMode.HTML)
    d["mst"] = mid
    bid = db_of(ctx).add(update.effective_user.id, d["name"], d["phone"], d["svc"], mid, start)
    await q.edit_message_text(
        summary(d, "✅ <b>Вы записаны!</b>") + f"\n\n📍 {ADDRESS}\n\n"
        "Напомним о визите за 2 часа. Отменить запись можно в разделе «📅 Мои записи».",
        parse_mode=ParseMode.HTML)
    schedule_reminder(ctx.application, bid, start)
    await notify_admin(ctx, "🆕 <b>Новая запись</b>\n\n" + admin_line(db_of(ctx).get(bid)))
    ctx.user_data.clear()


async def cancel_booking(update: Update, ctx: ContextTypes.DEFAULT_TYPE, bid: int):
    row = db_of(ctx).cancel(bid, update.effective_user.id)
    await update.callback_query.answer("Запись отменена" if row else "Эта запись уже неактивна")
    if row:
        for job in ctx.job_queue.get_jobs_by_name(f"remind-{bid}") if ctx.job_queue else []:
            job.schedule_removal()
        await notify_admin(ctx, "❌ <b>Клиент отменил запись</b>\n\n" + admin_line(row))
    await my_bookings(update, ctx, note="Запись отменена ✅\n\n" if row else "")


def admin_line(r) -> str:
    start = datetime.fromisoformat(r["start"])
    return (f"📅 {long_date(start)}\n✂️ {SERVICES[r['service']].title} · {master_name(r['master'])}\n"
            f"🙋 {r['name']}, {r['phone']}")


async def notify_admin(ctx, text: str):
    if config.ADMIN_ID:
        try:
            await ctx.bot.send_message(config.ADMIN_ID, text, parse_mode=ParseMode.HTML)
        except Exception:  # администратор мог не запускать бота — запись клиента от этого не должна сломаться
            log.exception("Не удалось отправить уведомление администратору")


# ---------- текст: имя, телефон, кнопки меню ----------

async def on_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    wait = ctx.user_data.get("wait")

    if text == CANCEL_WORD:
        ctx.user_data.clear()
        return await update.message.reply_text("Хорошо, не записываем.", reply_markup=MAIN_MENU)
    if text in MENU:  # кнопка меню прерывает ввод имени/телефона
        ctx.user_data.pop("wait", None)
        return await MENU[text](update, ctx)

    if wait == "name":
        if not 2 <= len(text) <= 40 or any(ch.isdigit() for ch in text):
            return await update.message.reply_text("Напишите, пожалуйста, просто имя — например, Олег.")
        draft(ctx)["name"] = text
        ctx.user_data["wait"] = "phone"
        return await update.message.reply_text(
            f"{text}, приятно познакомиться! Оставьте номер телефона — по нему мастер свяжется, если что-то изменится.",
            reply_markup=ReplyKeyboardMarkup([[KeyboardButton("📱 Отправить мой номер", request_contact=True)],
                                              [CANCEL_WORD]], resize_keyboard=True, one_time_keyboard=True))
    if wait == "phone":
        return await got_phone(update, ctx, text)

    await update.message.reply_text("Пользуйтесь кнопками меню внизу 👇", reply_markup=MAIN_MENU)


async def on_contact(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if ctx.user_data.get("wait") == "phone":
        await got_phone(update, ctx, update.message.contact.phone_number)


async def got_phone(update: Update, ctx: ContextTypes.DEFAULT_TYPE, raw: str):
    phone = format_phone(raw)
    if not phone:
        return await update.message.reply_text("Не похоже на номер 🤔 Напишите в формате +7 999 123-45-67.")
    d = draft(ctx)
    d["phone"] = phone
    ctx.user_data.pop("wait", None)
    await update.message.reply_text("Почти готово 👇", reply_markup=MAIN_MENU)
    text, markup = scr_confirm(d)
    await update.message.reply_text(text, reply_markup=markup, parse_mode=ParseMode.HTML)


MENU = {BTN_BOOK: book, BTN_MY: my_bookings, BTN_PRICE: prices, BTN_ROUTE: route}


# ---------- напоминания ----------

async def remind(ctx: ContextTypes.DEFAULT_TYPE):
    r = db_of(ctx).get(ctx.job.data)
    if not r or r["status"] != "active":
        return
    start = datetime.fromisoformat(r["start"])
    await ctx.bot.send_message(
        r["user_id"],
        f"⏰ Напоминаем: сегодня в <b>{start:%H:%M}</b> — {SERVICES[r['service']].title.lower()} "
        f"у мастера {master_name(r['master'])}.\n📍 {ADDRESS}\n\nЕсли планы изменились — отмените запись в «📅 Мои записи».",
        parse_mode=ParseMode.HTML)


def schedule_reminder(app: Application, bid: int, start: datetime):
    when = start - timedelta(minutes=config.REMIND_BEFORE_MIN)
    if app.job_queue and when > now():
        app.job_queue.run_once(remind, when=when.replace(tzinfo=config.TZ), data=bid, name=f"remind-{bid}")


async def restore_reminders(app: Application):
    """После перезапуска бота заново ставим напоминания на будущие записи."""
    for r in app.bot_data["db"].all_upcoming(now()):
        schedule_reminder(app, r["id"], datetime.fromisoformat(r["start"]))


# ---------- сборка ----------

def build_app(token: str, db: DB, request=None) -> Application:
    builder = Application.builder().token(token).post_init(restore_reminders)
    if request:
        builder = builder.request(request).get_updates_request(request)
    app = builder.build()
    app.bot_data["db"] = db
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("today", today))
    app.add_handler(CallbackQueryHandler(on_button))
    app.add_handler(MessageHandler(filters.CONTACT, on_contact))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    return app


def main():
    logging.basicConfig(format="%(asctime)s %(levelname)s %(message)s", level=logging.INFO)
    if not config.BOT_TOKEN:
        raise SystemExit("Не задан BOT_TOKEN. Скопируйте .env.example в .env и вставьте токен от @BotFather.")
    build_app(config.BOT_TOKEN, DB(config.DB_PATH)).run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
