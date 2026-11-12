"""Настройки читаются из файла .env рядом с ботом (образец — .env.example)."""
import os
from pathlib import Path
from zoneinfo import ZoneInfo


def _load_env(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


_load_env(Path(__file__).with_name(".env"))

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0") or 0)          # куда слать уведомления о записях
TZ = ZoneInfo(os.getenv("TIMEZONE", "Europe/Moscow"))
DB_PATH = os.getenv("DB_PATH", str(Path(__file__).with_name("bookings.db")))
REMIND_BEFORE_MIN = int(os.getenv("REMIND_BEFORE_MIN", "120"))
