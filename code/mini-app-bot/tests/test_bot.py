"""Проверка бота без интернета: заказ из Mini App, пересчёт цен, защита от подмены суммы.
Запуск из папки проекта:  python tests/test_bot.py"""
import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import bot  # noqa: E402
from telegram import Update  # noqa: E402
from tests.fake_telegram import FakeTelegram  # noqa: E402

USER, ADMIN = 501, 777
ok_count = fail_count = 0


def check(name, cond, detail=""):
    global ok_count, fail_count
    print(("OK   " if cond else "FAIL ") + name + (f"  [{detail}]" if detail and not cond else ""))
    ok_count, fail_count = ok_count + bool(cond), fail_count + (not cond)


def order_update(tg, app, data):
    mid = next(tg.ids)
    tg.chats[USER].append({"id": mid, "from": "user", "text": "🍕 Открыть меню (заказ из приложения)"})
    msg = {"message_id": mid, "date": int(time.time()), "chat": {"id": USER, "type": "private"},
           "from": tg.user(USER, "Олег"), "web_app_data": {"data": json.dumps(data, ensure_ascii=False), "button_text": "🍕 Открыть меню"}}
    return Update.de_json({"update_id": mid, "message": msg}, app.bot)


async def main():
    bot.ADMIN_ID = ADMIN
    tg = FakeTelegram()
    app = bot.build_app("1:TEST", request=tg)
    await app.initialize()
    last = lambda c: tg.last(c)["text"]  # noqa: E731

    await app.process_update(tg.text_update(app.bot, USER, "Олег", "/start"))
    check("Кнопка «Открыть меню» внизу", tg.keyboard[USER] == [["🍕 Открыть меню"]])

    good = {"items": [{"id": "pepp", "q": 2}, {"id": "lemon", "q": 1}], "mode": "delivery", "addr": "ул. Лесная, 8, кв. 12",
            "time": "asap", "note": "Домофон 12", "promo": "ТЕСТО10", "total": 1338}
    await app.process_update(order_update(tg, app, good))
    t = last(USER)
    check("Заказ принят", "Заказ №1043 принят" in t, t)
    check("Позиции и суммы пересчитаны ботом", "Пепперони × 2 — 1 298 ₽" in t and "Итого: 1 338 ₽" in t, t)
    check("Скидка по промокоду 10%", "−149 ₽" in t, t)
    check("Бесплатная доставка от 1000 ₽", "Доставка: бесплатно" in t, t)
    check("Администратор получил заказ с адресом", "Заказ №1043" in last(ADMIN) and "Лесная" in last(ADMIN))

    hacked = dict(good, total=1, items=[{"id": "pepp", "q": 1}], promo=None)
    await app.process_update(order_update(tg, app, hacked))
    check("Подмена суммы не работает (берётся цена бота)", "Итого: 798 ₽" in last(USER), last(USER))
    check("Платная доставка до 1000 ₽", "Доставка: 149 ₽" in last(USER), last(USER))

    await app.process_update(order_update(tg, app, {"items": [{"id": "nope", "q": 1}], "mode": "pickup"}))
    check("Несуществующий товар отклонён", "Не получилось" in last(USER))
    await app.process_update(order_update(tg, app, {"items": [{"id": "pepp", "q": 1}], "mode": "delivery", "addr": ""}))
    check("Доставка без адреса отклонена", "Не получилось" in last(USER))
    await app.process_update(order_update(tg, app, {"items": [{"id": "cola", "q": 1}], "mode": "pickup"}))
    check("Меньше минимальной суммы — отклонён", "Не получилось" in last(USER))
    await app.process_update(order_update(tg, app, {"items": [{"id": "cake", "q": 3}], "mode": "pickup", "time": "19:30"}))
    check("Самовывоз ко времени", "Самовывоз" in last(USER) and "Будет готов к 19:30" in last(USER), last(USER))

    await app.shutdown()
    print(f"\nПройдено {ok_count}, ошибок {fail_count}")
    if "--export" in sys.argv:
        tg.snapshot(USER, "user"); tg.snapshot(ADMIN, "admin")
        Path(sys.argv[sys.argv.index("--export") + 1]).write_text(json.dumps(tg.snaps, ensure_ascii=False), encoding="utf-8")
    return fail_count


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
