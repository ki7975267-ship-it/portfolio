"""Хранение записей в SQLite — отдельный сервер базы данных не нужен."""
import sqlite3
from datetime import date, datetime, timedelta

from data import SERVICES


class DB:
    def __init__(self, path: str = "bookings.db"):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS bookings (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id  INTEGER NOT NULL,
                name     TEXT NOT NULL,
                phone    TEXT NOT NULL,
                service  TEXT NOT NULL,
                master   TEXT NOT NULL,
                start    TEXT NOT NULL,           -- 2026-11-14T15:30, местное время салона
                status   TEXT NOT NULL DEFAULT 'active',
                created  TEXT NOT NULL
            )""")
        self.conn.commit()

    def add(self, user_id, name, phone, service, master, start: datetime) -> int:
        cur = self.conn.execute(
            "INSERT INTO bookings (user_id, name, phone, service, master, start, created) VALUES (?,?,?,?,?,?,?)",
            (user_id, name, phone, service, master, start.isoformat(timespec="minutes"),
             datetime.now().isoformat(timespec="seconds")))
        self.conn.commit()
        return cur.lastrowid

    def get(self, booking_id: int):
        return self.conn.execute("SELECT * FROM bookings WHERE id=?", (booking_id,)).fetchone()

    def busy(self, master: str, day: date) -> list[tuple[datetime, datetime]]:
        rows = self.conn.execute(
            "SELECT start, service FROM bookings WHERE master=? AND status='active' AND start LIKE ?",
            (master, day.isoformat() + "%")).fetchall()
        out = []
        for r in rows:
            s = datetime.fromisoformat(r["start"])
            out.append((s, s + timedelta(minutes=SERVICES[r["service"]].minutes)))
        return out

    def upcoming(self, user_id: int, now: datetime):
        return self.conn.execute(
            "SELECT * FROM bookings WHERE user_id=? AND status='active' AND start>=? ORDER BY start",
            (user_id, now.isoformat(timespec="minutes"))).fetchall()

    def all_upcoming(self, now: datetime):
        return self.conn.execute(
            "SELECT * FROM bookings WHERE status='active' AND start>=? ORDER BY start",
            (now.isoformat(timespec="minutes"),)).fetchall()

    def on_day(self, day: date):
        return self.conn.execute(
            "SELECT * FROM bookings WHERE status='active' AND start LIKE ? ORDER BY start",
            (day.isoformat() + "%",)).fetchall()

    def last_contact(self, user_id: int):
        return self.conn.execute(
            "SELECT name, phone FROM bookings WHERE user_id=? ORDER BY id DESC LIMIT 1", (user_id,)).fetchone()

    def cancel(self, booking_id: int, user_id: int):
        row = self.get(booking_id)
        if not row or row["user_id"] != user_id or row["status"] != "active":
            return None
        self.conn.execute("UPDATE bookings SET status='cancelled' WHERE id=?", (booking_id,))
        self.conn.commit()
        return row
