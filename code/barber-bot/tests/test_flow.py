"""Проверка бота «как живой клиент», без интернета.

Запуск из папки бота:  python tests/test_flow.py
С выгрузкой переписки:  python tests/test_flow.py --export dialog.json
"""
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import bot  # noqa: E402
import config  # noqa: E402
from db import DB  # noqa: E402
from tests.fake_telegram import FakeTelegram  # noqa: E402

NOW = datetime(2026, 11, 12, 11, 40)        # четверг, 11:40
OLEG, MARINA, ADMIN = 501, 502, 777
passed = failed = 0


def check(name, ok, detail=""):
    global passed, failed
    print(("OK   " if ok else "FAIL ") + name + (f"  [{detail}]" if detail and not ok else ""))
    passed, failed = passed + ok, failed + (not ok)


async def main(export: str | None):
    bot.now = lambda: NOW
    config.ADMIN_ID = ADMIN
    tg, db = FakeTelegram(), DB(":memory:")
    # чужие записи, чтобы часть времени была занята
    db.add(1, "Игорь", "+7 (900) 111-11-11", "combo", "artem", datetime(2026, 11, 14, 12, 0))
    db.add(2, "Пётр", "+7 (900) 222-22-22", "cut", "artem", datetime(2026, 11, 14, 17, 0))
    db.add(3, "Сергей", "+7 (900) 333-33-33", "beard", "artem", datetime(2026, 11, 14, 10, 30))
    app = bot.build_app("123:TEST", db, request=tg)
    await app.initialize()

    async def say(uid, name, text, contact=None):
        await app.process_update(tg.text_update(app.bot, uid, name, text, contact))

    async def press(uid, name, button):
        await app.process_update(tg.press_update(app.bot, uid, name, button))

    last = lambda uid: tg.last(uid)["text"]  # noqa: E731

    # 1. Знакомство
    await say(OLEG, "Олег", "/start")
    check("Приветствие по имени", "Привет, Олег" in last(OLEG))
    check("Главное меню внизу", tg.keyboard[OLEG] == [["✂️ Записаться"], ["📅 Мои записи", "💈 Услуги и цены"], ["📍 Как добраться"]])
    tg.snapshot(OLEG, "start")

    # 2. Полная запись
    await say(OLEG, "Олег", "✂️ Записаться")
    check("Список услуг", "Выберите услугу" in last(OLEG) and len(tg.last(OLEG)["inline"]) == 5)
    await press(OLEG, "Олег", "Мужская стрижка · 1 500 ₽")
    check("Выбор мастера", "К кому записать" in last(OLEG))
    tg.snapshot(OLEG, "masters")
    await press(OLEG, "Олег", "Артём — топ-барбер")
    days = sum(tg.last(OLEG)["inline"][:-1], [])
    check("7 дней, первый — «Сегодня»", days[0] == "Сегодня" and len(days) == 7, days)
    await press(OLEG, "Олег", "Сб 14")
    times = sum(tg.last(OLEG)["inline"][:-1], [])
    check("Занятое время скрыто (12:00–13:30 занято, 13:00 не влезает)", "12:00" not in times and "13:00" not in times and "11:00" in times, times)
    check("Стрижка не наезжает на запись в 17:00", "16:30" not in times and "16:00" in times, times)
    check("Время после закрытия не предлагается", times[-1] == "20:00", times[-1])
    tg.snapshot(OLEG, "times")
    await press(OLEG, "Олег", "15:30")
    check("Спрашивает имя", last(OLEG) == "Как вас зовут?")
    await say(OLEG, "Олег", "123")
    check("Цифры вместо имени не принимает", "просто имя" in last(OLEG))
    await say(OLEG, "Олег", "Олег")
    check("Просит телефон с кнопкой «Отправить номер»", tg.keyboard[OLEG][0] == ["📱 Отправить мой номер"])
    tg.snapshot(OLEG, "phone")
    await say(OLEG, "Олег", "12345")
    check("Неверный телефон не принимает", "Не похоже на номер" in last(OLEG))
    await say(OLEG, "Олег", "", contact="79991112233")
    check("Сводка перед подтверждением", "Проверьте запись" in last(OLEG) and "+7 (999) 111-22-33" in last(OLEG))
    check("Меню вернулось вниз", tg.keyboard[OLEG][0] == ["✂️ Записаться"])
    tg.snapshot(OLEG, "confirm")
    await press(OLEG, "Олег", "✅ Подтвердить")
    check("Запись подтверждена", "Вы записаны" in last(OLEG) and "сб, 14 ноября в 15:30" in last(OLEG), last(OLEG))
    check("Запись в базе", len(db.upcoming(OLEG, NOW)) == 1)
    check("Администратор получил уведомление", "Новая запись" in last(ADMIN) and "Олег" in last(ADMIN))
    jobs = app.job_queue.get_jobs_by_name("remind-4")
    run_at = jobs[0].job.trigger.run_date if jobs else None   # планировщик в тесте не запущен — берём время из триггера
    check("Напоминание поставлено за 2 часа (на 13:30)", run_at and (run_at.day, run_at.hour, run_at.minute) == (14, 13, 30),
          run_at)
    tg.snapshot(OLEG, "done")
    tg.snapshot(ADMIN, "admin")

    # 3. Повторная запись: бот помнит имя и телефон, время 15:30 у Артёма уже занято
    await say(OLEG, "Олег", "✂️ Записаться")
    await press(OLEG, "Олег", "Оформление бороды · 900 ₽")
    await press(OLEG, "Олег", "Артём — топ-барбер")
    await press(OLEG, "Олег", "Сб 14")
    times = sum(tg.last(OLEG)["inline"][:-1], [])
    check("Своё время 15:30 уже занято", "15:30" not in times and "16:30" in times, times)
    await press(OLEG, "Олег", "← Другой день")
    check("«Назад» возвращает к выбору дня", "Выберите день" in last(OLEG))
    await press(OLEG, "Олег", "Завтра")
    await press(OLEG, "Олег", "18:00")
    check("Узнаёт постоянного клиента", "Записать на имя <b>Олег</b>" in last(OLEG))
    await press(OLEG, "Олег", "Да, это я")
    await press(OLEG, "Олег", "✅ Подтвердить")
    check("Вторая запись", len(db.upcoming(OLEG, NOW)) == 2)

    # 4. Мои записи и отмена
    await say(OLEG, "Олег", "📅 Мои записи")
    check("Список записей", last(OLEG).count("📅") == 2)
    await press(OLEG, "Олег", "❌ Отменить 13.11 в 18:00")
    check("Отмена записи", "Запись отменена" in last(OLEG) and len(db.upcoming(OLEG, NOW)) == 1)
    check("Администратор узнал об отмене", "отменил" in last(ADMIN))
    check("Напоминание об отменённой записи снято", not any(j.enabled and not j.removed for j in app.job_queue.get_jobs_by_name("remind-5")))
    tg.snapshot(OLEG, "my")

    # 5. Гонка: пока Марина думала, это время занял другой клиент
    await say(MARINA, "Марина", "/start")
    await say(MARINA, "Марина", "✂️ Записаться")
    await press(MARINA, "Марина", "Детская стрижка · 1 000 ₽")
    await press(MARINA, "Марина", "Илья — фейды и укладки")
    await press(MARINA, "Марина", "Пн 16")
    await press(MARINA, "Марина", "11:00")
    await say(MARINA, "Марина", "Марина")
    await say(MARINA, "Марина", "8 (912) 555-44-33")
    check("Телефон, набранный вручную, тоже принимается", "+7 (912) 555-44-33" in last(MARINA))
    db.add(9, "Кто-то", "+7 (900) 999-99-99", "cut", "ilya", datetime(2026, 11, 16, 10, 30))
    await press(MARINA, "Марина", "✅ Подтвердить")
    check("Занятое в последний момент время не продаётся дважды", "только что заняли" in last(MARINA)
          and len(db.upcoming(MARINA, NOW)) == 0, last(MARINA))

    # 6. «Любой мастер»: Артём и Илья заняты — запись достаётся Денису
    await say(OLEG, "Олег", "✂️ Записаться")
    await press(OLEG, "Олег", "Мужская стрижка · 1 500 ₽")
    await press(OLEG, "Олег", "Любой свободный мастер")
    await press(OLEG, "Олег", "Вт 17")
    await press(OLEG, "Олег", "10:00")
    await press(OLEG, "Олег", "Да, это я")
    db.add(9, "Кто-то", "+7 (900) 999-99-99", "cut", "artem", datetime(2026, 11, 17, 10, 0))
    db.add(9, "Кто-то", "+7 (900) 999-99-99", "cut", "ilya", datetime(2026, 11, 17, 10, 0))
    await press(OLEG, "Олег", "✅ Подтвердить")
    check("«Любой мастер» → достался свободный Денис", "Денис" in last(OLEG) and "Вы записаны" in last(OLEG), last(OLEG))

    # 7. Устаревшая кнопка (например, после перезапуска бота)
    tg.chats[600].append({"id": 1, "from": "bot", "text": "старое", "inline": [["15:30"]], "_data": [["tm:1530"]]})
    await press(600, "Аня", "15:30")
    check("Старая кнопка не ломает бота", "устарела" in last(600))

    # 8. Кнопка меню во время ввода имени + сегодняшнее время
    await say(600, "Аня", "✂️ Записаться")
    await press(600, "Аня", "Мужская стрижка · 1 500 ₽")
    await press(600, "Аня", "Илья — фейды и укладки")
    await press(600, "Аня", "Сегодня")
    first = sum(tg.last(600)["inline"][:-1], [])[0]
    check("Сегодня — не раньше чем через 30 минут (сейчас 11:40)", first == "12:30", first)
    await press(600, "Аня", first)
    await say(600, "Аня", "💈 Услуги и цены")
    check("Кнопка меню не записывается как имя", "Услуги и цены" in last(600) and "1 500 ₽" in last(600))

    # 9. Админ-команда
    await say(ADMIN, "Админ", "/today")
    check("/today у администратора", "Сегодня записей нет" in last(ADMIN) or "Записи на сегодня" in last(ADMIN))
    before = len(tg.chats[OLEG])
    await say(OLEG, "Олег", "/today")
    check("/today недоступна клиенту", len(tg.chats[OLEG]) == before + 1)

    # 10. Напоминание приходит
    job = app.job_queue.get_jobs_by_name("remind-4")[0]
    await job.run(app)
    check("Напоминание отправлено клиенту", "Напоминаем" in last(OLEG) and "15:30" in last(OLEG))

    await app.shutdown()
    print(f"\nПройдено {passed}, ошибок {failed}")
    if export:
        Path(export).write_text(json.dumps(tg.snaps, ensure_ascii=False, indent=1), encoding="utf-8")
    return failed


if __name__ == "__main__":
    exp = sys.argv[sys.argv.index("--export") + 1] if "--export" in sys.argv else None
    sys.exit(asyncio.run(main(exp)))
