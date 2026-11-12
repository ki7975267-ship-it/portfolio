"""Услуги, мастера и расчёт свободного времени. Всё, что меняет владелец, — здесь."""
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

SALON = "Барбершоп «Щетина»"
ADDRESS = "ул. Лесная, 8 — вход с торца, 2 этаж"
HOURS = "Ежедневно с 10:00 до 21:00"


@dataclass(frozen=True)
class Service:
    id: str
    title: str
    price: int
    minutes: int


@dataclass(frozen=True)
class Master:
    id: str
    name: str
    about: str


SERVICES = {s.id: s for s in [
    Service("cut", "Мужская стрижка", 1500, 60),
    Service("combo", "Стрижка + борода", 2200, 90),
    Service("beard", "Оформление бороды", 900, 30),
    Service("kid", "Детская стрижка", 1000, 45),
]}

MASTERS = {m.id: m for m in [
    Master("artem", "Артём", "топ-барбер"),
    Master("ilya", "Илья", "фейды и укладки"),
    Master("denis", "Денис", "бороды и бритьё"),
]}

OPEN, CLOSE = time(10, 0), time(21, 0)
STEP_MIN = 30          # шаг сетки времени
DAYS_AHEAD = 7         # на сколько дней вперёд можно записаться
LEAD_MIN = 30          # не раньше, чем через 30 минут от «сейчас»

WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля",
          "августа", "сентября", "октября", "ноября", "декабря"]


def rub(n: int) -> str:
    return f"{n:,}".replace(",", " ") + " ₽"


def day_label(d: date, today: date) -> str:
    if d == today:
        return "Сегодня"
    if d == today + timedelta(days=1):
        return "Завтра"
    return f"{WEEKDAYS[d.weekday()]} {d.day}"


def day_title(d: date, today: date) -> str:
    label = day_label(d, today)
    head = label if label in ("Сегодня", "Завтра") else WEEKDAYS[d.weekday()].lower()
    return f"{head}, {d.day} {MONTHS[d.month - 1]}"


def long_date(dt: datetime) -> str:
    return f"{WEEKDAYS[dt.weekday()].lower()}, {dt.day} {MONTHS[dt.month - 1]} в {dt:%H:%M}"


def free_slots(day: date, minutes: int, busy: list[tuple[datetime, datetime]], now: datetime) -> list[datetime]:
    """Время начала, когда мастер свободен `minutes` минут подряд."""
    start = datetime.combine(day, OPEN)
    last = datetime.combine(day, CLOSE) - timedelta(minutes=minutes)
    earliest = now + timedelta(minutes=LEAD_MIN)
    slots = []
    while start <= last:
        end = start + timedelta(minutes=minutes)
        if start >= earliest and all(end <= b0 or start >= b1 for b0, b1 in busy):
            slots.append(start)
        start += timedelta(minutes=STEP_MIN)
    return slots
