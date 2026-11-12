"""Парсер интернет-магазина → отчёт Excel.

Собирает все товары каталога (название, категория, цена, рейтинг, остаток, артикул),
обходит страницы в несколько потоков, повторяет запросы при сбоях и строит Excel-отчёт
со сводкой по категориям и диаграммой.

Пример сайта — books.toscrape.com (учебный магазин, созданный специально для парсинга).

    python parser.py                    # весь каталог
    python parser.py --limit 100        # быстрый пробный запуск
    python parser.py --out отчёт.xlsx --threads 8
"""
import argparse
import logging
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from excel_report import save_report

BASE = "https://books.toscrape.com/"
RATING = {"One": 1, "Two": 2, "Three": 3, "Four": 4, "Five": 5}
# на сайте у части товаров вместо категории стоят заглушки — в отчёте объединяем их
PLACEHOLDER_CATEGORIES = {"Default", "Add a comment"}
NO_CATEGORY = "Без категории"
log = logging.getLogger("parser")


@dataclass
class Item:
    title: str
    url: str
    category: str
    price: float
    rating: int
    stock: int
    upc: str


def make_session() -> requests.Session:
    s = requests.Session()
    retry = Retry(total=4, backoff_factor=0.6, status_forcelist=[429, 500, 502, 503, 504])
    s.mount("https://", HTTPAdapter(max_retries=retry, pool_maxsize=32))
    s.headers["User-Agent"] = "Mozilla/5.0 (compatible; catalog-report/1.0)"
    return s


def soup(session, url: str) -> BeautifulSoup:
    r = session.get(url, timeout=20)
    r.raise_for_status()
    r.encoding = "utf-8"
    return BeautifulSoup(r.text, "html.parser")


def product_links(session, limit: int | None):
    """Идёт по страницам каталога, пока есть кнопка «next»."""
    url, links = urljoin(BASE, "catalogue/page-1.html"), []
    while url and (not limit or len(links) < limit):
        page = soup(session, url)
        links += [urljoin(url, a["href"]) for a in page.select("article.product_pod h3 a")]
        nxt = page.select_one("li.next a")
        url = urljoin(url, nxt["href"]) if nxt else None
    return links[:limit] if limit else links


def parse_item(session, url: str) -> Item:
    page = soup(session, url)
    info = {tr.th.text.strip(): tr.td.text.strip() for tr in page.select("table.table tr")}
    stock = re.search(r"\((\d+) available\)", info.get("Availability", ""))
    rating = next((RATING[c] for c in page.select_one("p.star-rating")["class"] if c in RATING), 0)
    category = page.select("ul.breadcrumb li a")[-1].text.strip()
    return Item(
        title=page.h1.text.strip(),
        url=url,
        category=NO_CATEGORY if category in PLACEHOLDER_CATEGORIES else category,
        price=float(re.sub(r"[^\d.]", "", page.select_one("p.price_color").text)),
        rating=rating,
        stock=int(stock.group(1)) if stock else 0,
        upc=info.get("UPC", ""),
    )


def plural(n: int, one: str, few: str, many: str) -> str:
    """1 категория, 2 категории, 5 категорий."""
    if n % 10 == 1 and n % 100 != 11:
        return f"{n} {one}"
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return f"{n} {few}"
    return f"{n} {many}"


def progress(done: int, total: int, started: float):
    width = 30
    fill = int(width * done / total)
    speed = done / max(time.time() - started, 0.001)
    sys.stdout.write(f"\r  [{'█' * fill}{'·' * (width - fill)}] {done}/{total}  {speed:5.1f} стр/с ")
    sys.stdout.flush()


def main():
    ap = argparse.ArgumentParser(description="Парсер каталога → Excel")
    ap.add_argument("--limit", type=int, help="сколько товаров собрать (по умолчанию все)")
    ap.add_argument("--threads", type=int, default=8, help="потоков одновременно (по умолчанию 8)")
    ap.add_argument("--out", default=f"Каталог {datetime.now():%Y-%m-%d}.xlsx", help="имя файла Excel")
    args = ap.parse_args()
    logging.basicConfig(filename="parser.log", level=logging.INFO, encoding="utf-8",
                        format="%(asctime)s %(levelname)s %(message)s")

    started = time.time()
    session = make_session()
    print("1/3  Собираю ссылки на товары…")
    links = product_links(session, args.limit)
    print(f"     найдено: {len(links)}")

    print(f"2/3  Загружаю карточки товаров ({args.threads} потоков)…")
    items, failed = [], []
    with ThreadPoolExecutor(max_workers=args.threads) as pool:
        futures = {pool.submit(parse_item, session, u): u for u in links}
        for i, f in enumerate(as_completed(futures), 1):
            try:
                items.append(f.result())
            except Exception as e:          # одна сломанная карточка не должна останавливать сбор
                failed.append(futures[f])
                log.warning("Ошибка %s: %s", futures[f], e)
            progress(i, len(links), started)
    print()
    for u in list(failed):                  # вторая попытка для упавших
        try:
            items.append(parse_item(session, u))
            failed.remove(u)
        except Exception as e:
            log.error("Не удалось: %s: %s", u, e)

    print("3/3  Строю отчёт Excel…")
    items.sort(key=lambda x: (x.category == NO_CATEGORY, x.category, x.title))
    save_report(items, args.out, source=BASE)
    secs = time.time() - started
    cats = len({i.category for i in items})
    print(f"\nГотово за {secs:.0f} с: {plural(len(items), 'товар', 'товара', 'товаров')}, "
          f"{plural(cats, 'категория', 'категории', 'категорий')}, ошибок: {len(failed)}\nФайл: {args.out}")
    log.info("Готово: %s товаров за %.1f с, ошибок %s", len(items), secs, len(failed))


if __name__ == "__main__":
    main()
