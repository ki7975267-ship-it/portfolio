"""Красивый отчёт Excel: товары, сводка по категориям с диаграммой, подборка лучших."""
from collections import defaultdict
from datetime import datetime
from statistics import mean

from openpyxl import Workbook
from openpyxl.chart import BarChart, Reference
from openpyxl.formatting.rule import ColorScaleRule, DataBarRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table, TableStyleInfo

INK, ACCENT, SOFT = "1F2A37", "E8A44A", "F4F1EC"
HEAD = Font(bold=True, color="FFFFFF")
HEAD_FILL = PatternFill("solid", fgColor=INK)
PRICE = '0.00 "£"'
THIN = Border(bottom=Side(style="thin", color="E2DED6"))


def stars(n: int) -> str:
    return "★" * n + "☆" * (5 - n)


def header(ws, row, titles, widths):
    for col, (t, w) in enumerate(zip(titles, widths), 1):
        c = ws.cell(row=row, column=col, value=t)
        c.font, c.fill = HEAD, HEAD_FILL
        c.alignment = Alignment(vertical="center", horizontal="center", wrap_text=True)
        ws.column_dimensions[get_column_letter(col)].width = w
    ws.row_dimensions[row].height = 30


def save_report(items, path: str, source: str = ""):
    wb = Workbook()

    # --- Лист 1: все товары ---
    ws = wb.active
    ws.title = "Товары"
    cols = ["№", "Название", "Категория", "Цена", "Рейтинг", "Оценка", "В наличии, шт", "Артикул (UPC)"]
    header(ws, 1, cols, [6, 52, 20, 11, 10, 11, 14, 20])
    for i, it in enumerate(items, 1):
        ws.append([i, it.title, it.category, it.price, it.rating, stars(it.rating), it.stock, it.upc])
        t = ws.cell(row=i + 1, column=2)
        t.hyperlink, t.style = it.url, "Hyperlink"
    last = len(items) + 1
    for r in ws.iter_rows(min_row=2, max_row=last):
        r[3].number_format = PRICE
        r[5].font = Font(color=ACCENT)
        for c in (r[0], r[4], r[5], r[6]):
            c.alignment = Alignment(horizontal="center")
    table = Table(displayName="Товары", ref=f"A1:H{last}")
    table.tableStyleInfo = TableStyleInfo(name="TableStyleLight1", showRowStripes=True)
    ws.add_table(table)
    ws.conditional_formatting.add(f"D2:D{last}", ColorScaleRule(start_type="min", start_color="D8F0DD",
                                                                 mid_type="percentile", mid_value=50, mid_color="FFFFFF",
                                                                 end_type="max", end_color="F8D7CF"))
    ws.conditional_formatting.add(f"G2:G{last}", DataBarRule(start_type="min", end_type="max", color="7FB3E0"))
    ws.freeze_panes = "C2"

    # --- Лист 2: сводка по категориям ---
    sm = wb.create_sheet("Сводка")
    by_cat = defaultdict(list)
    for it in items:
        by_cat[it.category].append(it)
    sm["A1"] = "Сводка по каталогу"
    sm["A1"].font = Font(size=18, bold=True, color=INK)
    sm["A2"] = f"Источник: {source}   ·   Собрано: {datetime.now():%d.%m.%Y %H:%M}"
    sm["A2"].font = Font(color="8A8F94")
    kpis = [("Товаров", len(items), "0"), ("Категорий", len(by_cat), "0"),
            ("Средняя цена", mean(i.price for i in items), PRICE),
            ("Всего на складе, шт", sum(i.stock for i in items), "#,##0"),
            ("С оценкой 5★", sum(i.rating == 5 for i in items), "0")]
    for col, (name, val, fmt) in enumerate(kpis, 1):
        n = sm.cell(row=4, column=col, value=name)
        v = sm.cell(row=5, column=col, value=val)
        n.font, n.fill = Font(color="6B7280", size=10), PatternFill("solid", fgColor=SOFT)
        v.font, v.fill, v.number_format = Font(size=16, bold=True, color=INK), PatternFill("solid", fgColor=SOFT), fmt
        for c in (n, v):
            c.alignment = Alignment(horizontal="left", indent=1)
    sm.row_dimensions[5].height = 28

    top = 7
    header(sm, top, ["Категория", "Товаров", "Средняя цена", "Мин. цена", "Макс. цена", "Средний рейтинг", "На складе, шт"],
           [24, 11, 14, 12, 12, 15, 14])
    rows = sorted(by_cat.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    for r, (cat, its) in enumerate(rows, top + 1):
        prices = [i.price for i in its]
        vals = [cat, len(its), mean(prices), min(prices), max(prices), round(mean(i.rating for i in its), 1),
                sum(i.stock for i in its)]
        for c, v in enumerate(vals, 1):
            cell = sm.cell(row=r, column=c, value=v)
            cell.border = THIN
            if 3 <= c <= 5:
                cell.number_format = PRICE
            if c == 6:
                cell.number_format = "0.0"
            if c >= 2:
                cell.alignment = Alignment(horizontal="center")
    end = top + len(rows)
    sm.conditional_formatting.add(f"B{top + 1}:B{end}", DataBarRule(start_type="num", start_value=0, end_type="max", color=ACCENT))
    sm.freeze_panes = sm.cell(row=top + 1, column=1)

    chart = BarChart()
    chart.type, chart.style = "bar", 10
    chart.title = "Топ-15 категорий по числу товаров"
    chart.y_axis.title, chart.legend = "Товаров", None
    n = min(15, len(rows))
    chart.add_data(Reference(sm, min_col=2, min_row=top, max_row=top + n), titles_from_data=True)
    chart.set_categories(Reference(sm, min_col=1, min_row=top + 1, max_row=top + n))
    chart.x_axis.scaling.orientation = "maxMin"     # самая большая категория сверху
    chart.series[0].graphicalProperties.solidFill = ACCENT
    chart.height, chart.width = 11, 17
    sm.add_chart(chart, "I7")

    # --- Лист 3: лучшие по оценке и цене ---
    best = wb.create_sheet("Лучшее")
    best["A1"] = "Оценка 5★ — от самых доступных"
    best["A1"].font = Font(size=16, bold=True, color=INK)
    header(best, 3, ["Название", "Категория", "Цена", "В наличии, шт"], [52, 20, 11, 14])
    picks = sorted((i for i in items if i.rating == 5), key=lambda i: i.price)[:30]
    for r, it in enumerate(picks, 4):
        best.cell(row=r, column=1, value=it.title).hyperlink = it.url
        best.cell(row=r, column=1).style = "Hyperlink"
        best.cell(row=r, column=2, value=it.category)
        best.cell(row=r, column=3, value=it.price).number_format = PRICE
        best.cell(row=r, column=4, value=it.stock).alignment = Alignment(horizontal="center")
        for c in range(1, 5):
            best.cell(row=r, column=c).border = THIN

    wb.active = 1          # открывается сразу на сводке
    wb.save(path)
