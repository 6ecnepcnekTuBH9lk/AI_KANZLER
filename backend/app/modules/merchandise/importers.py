"""Source-specific interpretation layered over semantic, position-independent reading."""

import re
from collections import Counter
from datetime import date, timedelta

from app.core.exceptions import InputError
from app.shared.excel import as_date, fraction, norm, number, read_tables

MONTHS = {
    "янв": 1,
    "фев": 2,
    "мар": 3,
    "апр": 4,
    "май": 5,
    "июн": 6,
    "июл": 7,
    "авг": 8,
    "сен": 9,
    "окт": 10,
    "ноя": 11,
    "дек": 12,
}
ALIASES = {
    "article": ["Артикул"],
    "code": ["Код"],
    "category": ["Категория", "Группа видов номенклатуры", "Группа"],
    "kind": ["Вид номенклатуры"],
    "assortment": ["Вид ассортимента"],
    "season": ["Коллекция (сезон)", "Коллекция", "Сезон"],
    "base": ["Начальный остаток"],
    "stock": ["Конечный остаток", "Текущий остаток", "Остаток"],
    "store_date": [
        "Дата первого поступления на магазины",
        "Дата поступления в магазины",
        "Дата входа в магазины",
    ],
    "sales_date": ["Дата начала продаж"],
    "warehouse_date": ["Дата первого поступления на ОС", "Дата первого поступления на основные склады"],
    "price": ["Цена со скидкой (RUB)", "Текущая цена", "Цена со скидкой", "Цена"],
    "discount": ["Скидка (%)", "Текущая скидка", "Скидка"],
    "markup": ["Markup Факт", "Наценка", "Markup"],
    "margin": ["Маржа годовых продаж (%)", "Маржа", "Маржа (%)"],
    "sizes": ["Общее количество размеров", "Размеров всего", "Количество размеров"],
    "avg_sizes": ["Среднее количество размеров", "Среднее размеров"],
    "size_availability": ["Коэффициент размерной доступности", "К. полноты размеров"],
    "broken_ratio": ["Доля магазинов с выбитостью (%)", "Доля магазинов с выбитостью"],
    "stores": ["Количество магазинов с остатком", "Магазинов с остатком"],
    "effective_stores": ["Эффективное количество магазинов", "Эффективных магазинов"],
    "warehouse": ['Остатки "Основные Склады"', "ОСНОВНЫЕ СКЛАДЫ", "Складской остаток"],
    "distribution": ["Коэффициент распределения продаж (%)", "Коэффициент распределения"],
    "sales_total": ["Продано за год", "Продано за 12 мес", "Накопительные продажи"],
    "first_batch_sales": ["Продажи первой партии"],
    "second_actual": ["Фактическая дата 2-й поставки"],
    "gross_profit": ["Валовая прибыль"],
    "avg_cost_stock": ["Средний запас по себестоимости"],
    "repricing_date": ["Дата последней переоценки"],
}
BOOLEAN_FIELDS = {
    "representation_ok": "Представленность достаточна",
    "sizes_ok": "Ходовые размеры доступны",
    "distribution_ok": "Распределение корректно",
    "replenishment_ok": "Подсортировка проверена",
    "stop_checked": "Остановка подсортировки проверена",
    "stores_checked": "Сокращение магазинов проверено",
    "warehouse_checked": "Перераспределение через склад проверено",
    "channel_checked": "Смена канала проверена",
    "economics_ok": "Экономика второй поставки подтверждена",
    "capacity_ok": "Запас второй поставки допустим",
    "channel_ok": "Канал второй поставки подтвержден",
    "price_room": "Ценовой потенциал подтвержден",
    "price_effect": "Эффект переоценки подтвержден",
    "seasonality_confirmed": "Сезонность подтверждена",
}


def parse_season(text):
    text = norm(text).replace(" ", "")
    match = re.search(r"(?<![а-яa-z])(оз|вл|осень[-–]?зима|весна[-–]?лето)(?:20)?(\d{2})", text)
    if match:
        return ("ОЗ" if match[1] in ("оз", "осень-зима", "осеньзима", "осень–зима") else "ВЛ") + match[2]
    return None


def month_of(header):
    s = norm(header).split("/")[-1].strip()
    for word, month in MONTHS.items():
        if s.startswith(word):
            return month
    d = as_date(header)
    return d.month if d else None


def select_table(tables, role):
    def score(t):
        if role == "fact":
            return 100 if t.col("Начальный остаток") is not None and t.col("Артикул") is not None else 0
        if role == "article":
            return (
                (100 + sum(month_of(h) is not None for h in t.headers))
                if t.col("Артикул") is not None
                and t.col(
                    "% продаж к дате",
                    "Целевой процент реализации сезона",
                    "Целевой Sell-through",
                    "Target ST",
                )
                is not None
                else 0
            )
        return (
            100
            if t.col("Артикул") is None
            and t.col("Вид номенклатуры") is not None
            and t.col("Вид ассортимента") is not None
            else 0
        )

    candidates = [t for t in tables if score(t)]
    if not candidates:
        return None
    return max(candidates, key=score)


def detect_roles(files):
    roles = {}
    for f in files:
        tables = read_tables(f.path)
        detected = [(r, select_table(tables, r)) for r in ("fact", "article", "category")]
        detected = [(r, t) for r, t in detected if t]
        # ARTICLE PLAN may include cached fact columns; target and monthly form distinguish role.
        if any(r == "article" for r, t in detected):
            detected = [(r, t) for r, t in detected if r == "article"]
        if len(detected) != 1:
            raise InputError(f"Не удалось однозначно определить роль файла «{f.original_name}».")
        role, table = detected[0]
        if role in roles:
            raise InputError("Найдено несколько версий одного типа файла. Оставьте одну актуальную версию.")
        roles[role] = (f, table)
    if set(roles) != {"fact", "article", "category"}:
        raise InputError(
            "Для анализа нужны поартикульный план, категорийный план и актуальный анализ продаж."
        )
    return roles


def weekly_columns(table):
    result = []
    for i, path in enumerate(table.paths):
        if "за день" in norm(path):
            continue
        if not any(x in norm(path) for x in ("недел", "количество продано", "продажи")):
            continue
        dates = [as_date(row[i].value) for row in table.preamble if i < len(row)]
        d = next((d for d in dates if d), None) or as_date(path)
        if d:
            result.append((i, d))
    return result


def metadata(roles, options):
    qa = []
    af, article = roles["article"]
    ff, fact = roles["fact"]
    cf, _category = roles["category"]
    candidates = set()
    for row in article.preamble:
        for cell in row:
            if s := parse_season(cell.value):
                candidates.add(s)
    for _, row in article.rows:
        if s := parse_season(article.get(row, "Сезон", "Коллекция")):
            candidates.add(s)
    if not candidates and (s := parse_season(af.original_name)):
        candidates.add(s)
    if not candidates and any(
        str(article.get(row, "Артикул") or "").startswith("6A") for _, row in article.rows
    ):
        candidates.add("ОЗ26")
    season = options.get("season") or (next(iter(candidates)) if len(candidates) == 1 else None)
    if not season:
        raise InputError(
            "Не удалось однозначно определить сезон.", {"needs": ["season"], "candidates": sorted(candidates)}
        )
    cseason = parse_season(cf.original_name)
    if cseason and cseason != season and not options.get("season"):
        raise InputError(
            "Сезон категорийного плана противоречит поартикульному плану.", {"needs": ["season"]}
        )
    explicit_dates = set()
    for row in fact.preamble:
        for i, cell in enumerate(row):
            if any(w in norm(cell.value) for w in ("дата анализа", "контрольная дата", "анализ на")):
                d = as_date(cell.value) or (as_date(row[i + 1].value) if i + 1 < len(row) else None)
                if d:
                    explicit_dates.add(d)
    named_date = as_date(ff.original_name)
    weeks = weekly_columns(fact)
    last_week = max((d for _, d in weeks), default=None)
    control = as_date(options.get("control_date")) or (
        next(iter(explicit_dates)) if len(explicit_dates) == 1 else named_date
    )
    if len(explicit_dates) > 1 and not options.get("control_date"):
        raise InputError("В файле несколько контрольных дат.", {"needs": ["control_date"]})
    if not control and last_week:
        control = last_week + timedelta(days=6)
        qa.append(("Дата анализа определена по последней фактической неделе.", "Предупреждение"))
    if not control:
        raise InputError("Не удалось определить контрольную дату.", {"needs": ["control_date"]})
    if not options.get("control_date") and (
        (explicit_dates and named_date and named_date != control) or (last_week and last_week > control)
    ):
        raise InputError(
            "Контрольная дата противоречит содержимому фактических продаж.", {"needs": ["control_date"]}
        )
    if options:
        qa.append(("Применены явные уточнения параметров анализа пользователем.", "Информация"))
    if season == "ОЗ26":
        start, end = date(2026, 9, 1), date(2027, 2, 28)
    else:
        starts = {as_date(article.get(r, "Начало сезона")) for _, r in article.rows} - {None}
        ends = {as_date(article.get(r, "Конец сезона")) for _, r in article.rows} - {None}
        start = as_date(options.get("season_start")) or (next(iter(starts)) if len(starts) == 1 else None)
        end = as_date(options.get("season_end")) or (next(iter(ends)) if len(ends) == 1 else None)
        if not start or not end or end < start:
            raise InputError("Не найдено официальное окно сезона.", {"needs": ["season_start", "season_end"]})
    if last_week and (control - last_week).days > 6:
        qa.append(
            (
                "Последняя фактическая неделя отстаёт от контрольной даты; отсутствующие периоды не считаются нулевыми продажами.",
                "Предупреждение",
            )
        )
    for i, d in weeks:
        match = re.search(r"неделя\s+(\d+)", norm(fact.paths[i]))
        if match and int(match[1]) != d.isocalendar().week:
            qa.append(
                (
                    "Подписи номеров недель расходятся с календарём; использованы явные даты начала недель.",
                    "Информация",
                )
            )
            break
    return season, control, start, end, qa


def read_fact(table, season, articles):
    weekly = weekly_columns(table)
    result = []
    for ri, row in table.rows:
        article = str(table.get(row, "Артикул") or "").strip()
        if not article or norm(article) in ("итого", "артикул", "общий итог"):
            continue
        if season == "ОЗ26" and not article.startswith("6A"):
            continue
        if season != "ОЗ26" and article not in articles:
            continue
        out = {"source_row": ri}
        for key, aliases in ALIASES.items():
            value = table.get(row, *aliases)
            if key in ("article", "code", "category", "kind", "assortment", "season"):
                out[key] = str(value or "").strip()
            elif key.endswith("_date") or key == "second_actual":
                out[key] = as_date(value)
            elif key in ("discount", "margin", "size_availability", "broken_ratio", "distribution"):
                ci = table.col(*aliases)
                # Exported 1C TDSheet percentages are whole percentages, even 0 and 1.
                out[key] = fraction(
                    value, row[ci].fmt if ci is not None else "", whole=table.sheet == "TDSheet"
                )
            else:
                out[key] = number(value)
        out["article"] = article
        out["weekly"] = {d: number(row[i].value) for i, d in weekly}
        # Daily data, when provided, overrides boundary-week proration.
        out["daily"] = {}
        for i, path in enumerate(table.paths):
            if norm(path).startswith("продажи за день") and (d := as_date(path)):
                out["daily"][d] = number(row[i].value)
        for key, header in BOOLEAN_FIELDS.items():
            value = norm(table.get(row, header))
            out[key] = True if value == "да" else False if value == "нет" else None
        out["line"] = str(table.get(row, "Линия", "Линейка") or "")
        out["repricing_stage"] = str(table.get(row, "Этап переоценки") or "")
        out["planned_stores"] = number(table.get(row, "План магазинов"))
        out["warehouse"] = (
            sum(
                number(table.get(row, header)) or 0
                for header in (
                    'Остатки "Основные Склады"',
                    'Остатки "Основные Склады Казахстан"',
                    'Остатки "Основные Склады Екатеринбург"',
                    'Остатки "Основные Склады Новосибирск"',
                )
            )
            if table.col('Остатки "Основные Склады"') is not None
            else out["warehouse"]
        )
        if out["size_availability"] is None and out["sizes"] and out["avg_sizes"] is not None:
            out["size_availability"] = out["avg_sizes"] / out["sizes"]
        out["channel_distribution"] = {
            h: number(row[i].value) for i, h in enumerate(table.headers) if "распределение " in norm(h)
        }
        result.append(out)
    return result


def read_plans(table, category=False):
    result = []
    for ri, row in table.rows:
        identity = table.get(row, "Вид номенклатуры" if category else "Артикул")
        if identity is None or norm(identity) in ("итого", "общий итог", "артикул"):
            continue
        item = {
            "article": str(identity).strip() if not category else None,
            "code": str(table.get(row, "Код") or "").strip(),
            "category": str(table.get(row, "Категория") or ""),
            "kind": str(table.get(row, "Вид номенклатуры") or ""),
            "assortment": str(table.get(row, "Вид ассортимента") or ""),
            "source_row": ri,
            "months": {},
            "month_mode": "units",
            "weekly_plan": {},
            "target": fraction(
                table.get(
                    row,
                    "% продаж к дате",
                    "Целевой процент реализации сезона",
                    "Целевой Sell-through",
                    "Target ST",
                )
            ),
            "entry": as_date(table.get(row, "Дата входа")),
            "type": str(table.get(row, "Тип сезонности") or ""),
            "deadline": as_date(table.get(row, "Коммерческое окно", "Окончание окна")),
            "term": str(table.get(row, "Целевой срок реализации", "Нормативный срок реализации") or ""),
            "second_date": as_date(table.get(row, "Дата 2-й поставки", "Дата второй поставки")),
            "second_qty": number(table.get(row, "2-я партия", "Объём 2-й поставки", "Объем 2-й поставки")),
            "monthly_discount": {},
            "monthly_markup": {},
        }
        modes = {"pct": {}, "units": {}, "cumulative": {}}
        for ci, path in enumerate(table.paths):
            month = month_of(table.headers[ci])
            p = norm(path)
            if month:
                if "скидк" in p:
                    item["monthly_discount"][month] = fraction(row[ci].value, row[ci].fmt)
                elif "markup" in p or "наценк" in p:
                    item["monthly_markup"][month] = number(row[ci].value)
                elif any(w in p for w in ("выручк", "себестоим", "цена")):
                    continue
                elif "накопительн" in p:
                    modes["cumulative"][month] = fraction(row[ci].value, row[ci].fmt)
                elif "%" in p or "%" in row[ci].fmt:
                    modes["pct"][month] = fraction(row[ci].value, row[ci].fmt)
                elif not category or "проданным единицам" in p:
                    modes["units"][month] = number(row[ci].value)
            if "план неделя" in p and (m := re.search(r"неделя\s+(\d+)\s+(\d{4})", p)):
                try:
                    d = date.fromisocalendar(int(m[2]), int(m[1]), 1)
                    item["weekly_plan"][d] = fraction(row[ci].value, row[ci].fmt)
                except ValueError:
                    continue
        if modes["pct"]:
            item["months"], item["month_mode"] = modes["pct"], "pct"
        elif modes["units"]:
            item["months"] = modes["units"]
        elif modes["cumulative"]:
            previous = 0
            for month in (9, 10, 11, 12, 1, 2):
                val = modes["cumulative"].get(month)
                item["months"][month] = val - previous if val is not None else None
                previous = val if val is not None else previous
            item["month_mode"] = "pct"
        if category and item["target"] is None and modes["cumulative"]:
            item["target"] = modes["cumulative"].get(2)
        if (
            category
            and item["target"] is None
            and item["month_mode"] == "pct"
            and all(v is not None for v in item["months"].values())
        ):
            item["target"] = sum(item["months"].values())
        result.append(item)
    return result


def duplicate_keys(rows, key):
    return {k for k, n in Counter(key(r) for r in rows).items() if k and n > 1}
