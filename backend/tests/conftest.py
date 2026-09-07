from datetime import date, timedelta
from types import SimpleNamespace

import pytest
from openpyxl import Workbook


@pytest.fixture
def commercial_files(tmp_path):
    """Explicit synthetic test fixture; never a production resource."""
    specs = [
        (
            "Поартикульный план ОЗ26.xlsx",
            [
                "Артикул",
                "Код",
                "Категория",
                "Тип сезонности",
                "Дата входа",
                "% продаж к дате",
                "Сен",
                "Окт",
                "Ноя",
                "Дек",
                "Янв",
                "Фев",
                "1-я партия",
                "Дата 2-й поставки",
                "2-я партия",
            ],
            [
                "6A-TEST",
                "001",
                "Брюки",
                "сезонный",
                date(2026, 8, 1),
                0.7,
                10,
                15,
                20,
                25,
                20,
                10,
                999999,
                date(2026, 12, 1),
                100,
            ],
        ),
        (
            "Категорийный план ОЗ26.xlsx",
            [
                "Вид номенклатуры",
                "Вид ассортимента",
                "Целевой процент реализации сезона",
                "Сен",
                "Окт",
                "Ноя",
                "Дек",
                "Янв",
                "Фев",
            ],
            ["Брюки", "Брюки", 0.7, 10, 15, 20, 25, 20, 10],
        ),
    ]
    files = []
    for name, headers, values in specs:
        wb = Workbook()
        ws = wb.active
        ws.append(headers)
        ws.append(values)
        path = tmp_path / name
        wb.save(path)
        files.append(SimpleNamespace(path=path, original_name=name))
    wb = Workbook()
    ws = wb.active
    starts = [date(2026, 8, 3) + timedelta(days=7 * i) for i in range(9)]
    headers = [
        "Артикул",
        "Код",
        "Вид номенклатуры",
        "Вид ассортимента",
        "Начальный остаток",
        "Конечный остаток",
        "Дата поступления в магазины",
        "Текущая цена",
        "Скидка",
        "Наценка",
        "Маржа",
        "Количество размеров",
        "Среднее размеров",
        "Количество магазинов с остатком",
        "Представленность достаточна",
        "Ходовые размеры доступны",
        "Распределение корректно",
    ]
    headers += [f"Продажи неделя {d.isoformat()}" for d in starts]
    ws.append(headers)
    ws.append(
        [
            "6A-TEST",
            "001",
            "Брюки",
            "Брюки",
            1000,
            750,
            date(2026, 8, 1),
            10000,
            0,
            3,
            0.67,
            6,
            6,
            20,
            "Да",
            "Да",
            "Да",
        ]
        + [10, 20, 30, 40, 70, 40, 35, 30, 25]
    )
    name = "Анализ продаж 2026-10-04.xlsx"
    path = tmp_path / name
    wb.save(path)
    files.append(SimpleNamespace(path=path, original_name=name))
    return files


@pytest.fixture
def merchandise_fact():
    return {
        "article": "6A-TEST",
        "code": "001",
        "category": "Брюки",
        "kind": "Брюки",
        "assortment": "Брюки",
        "base": 1000,
        "stock": 600,
        "weekly": {date(2026, 9, 7): 40, date(2026, 9, 14): 50, date(2026, 9, 21): 60, date(2026, 9, 28): 70},
        "daily": {},
        "store_date": date(2026, 8, 1),
        "sales_date": None,
        "warehouse_date": None,
        "sales_total": 300,
        "warehouse": 100,
        "price": 10000,
        "discount": 0.1,
        "margin": 0.6,
        "markup": 3,
        "first_batch_sales": None,
        "second_actual": None,
    }


@pytest.fixture
def article_plan():
    return {
        "article": "6A-TEST",
        "code": "001",
        "category": "Брюки",
        "months": {9: 10, 10: 20, 11: 30, 12: 20, 1: 10, 2: 10},
        "month_mode": "units",
        "target": 0.7,
        "entry": date(2026, 8, 1),
        "deadline": None,
        "term": "",
        "type": "сезонный",
        "second_date": None,
        "second_qty": None,
        "weekly_plan": {},
    }
