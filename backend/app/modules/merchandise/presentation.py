"""Presentation only: never use rounded quantities as calculation inputs."""

from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal

UNIT_KEYS = {
    "base",
    "season_plan",
    "plan_units",
    "preseason",
    "season_fact",
    "gap_units",
    "previous_week",
    "current_week",
    "forecast",
    "stock",
    "second_qty",
    "first_sales",
    "target70",
    "remaining70",
    "scenario_forecast",
    "gap",
    "monthly_units",
    "quantity",
    "known_base_units",
    "known_plan_units",
    "known_fact_units",
    "known_forecast_units",
    "count",
    "total_articles",
    "base_known_articles",
    "plan_known_articles",
    "fact_known_articles",
    "forecast_known_articles",
    "comparable_articles",
    "st_comparable_articles",
    "execution_comparable_articles",
    "affected_articles",
    "occurrences",
    "season_observation_days",
    "hits",
    "on_plan",
    "risks",
    "outsiders",
}


def display_units(value):
    return None if value is None else int(Decimal(str(value)).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def deduplicate_quality(rows):
    unique = {}
    for row in rows:
        unique.setdefault((row.get("article"), row.get("source"), row["message"]), row)
    return list(unique.values())


def group_quality(rows):
    groups = defaultdict(list)
    for row in deduplicate_quality(rows):
        groups[(row["severity"], row["source"], row["message"])].append(row)
    return [
        {
            "severity": severity,
            "source": source,
            "message": message,
            "affected_articles": len({r["article"] for r in items if r.get("article")}),
            "occurrences": len(items),
        }
        for (severity, source, message), items in groups.items()
    ]


def summary_rows(summary, display):
    mappings = {
        "Суммарный начальный остаток": ("base", "База — начальный остаток из фактических данных."),
        "План на дату, ед.": ("plan_units", "Известный план; отсутствующие значения не заменены нулём."),
        "Факт продаж сезона, ед.": ("season_fact", "Продажи только внутри официального сезона."),
        "Прогноз продаж, ед.": ("forecast", "Условный прогноз по доступному устойчивому темпу."),
        "Продажи до начала сезона, ед. — оценка": (
            "preseason",
            "Известный предсезон отдельно; не входит в выполнение сезона.",
        ),
    }
    rows = []
    for label, value in display.items():
        kind, coverage, meaning = "text", "", "Контекст анализа."
        if label in mappings:
            key, meaning = mappings[label]
            c = summary["coverage"][key]
            value, kind = c["known_sum"], "units"
            coverage = f"{c['known_count']} / {summary['count']} артикулов"
        elif label in ("Факт реализации сезона, %", "Выполнение плана на дату, %", "План на дату, %"):
            key = {
                "Факт реализации сезона, %": "st",
                "Выполнение плана на дату, %": "execution",
                "План на дату, %": "plan_pct",
            }[label]
            value, kind = summary[key], "percent"
            coverage = f"{summary[key + '_comparable_articles']} сопоставимых артикулов"
            meaning = "Отношение сумм на одном наборе с обоими известными показателями."
        elif isinstance(value, (int, float)):
            kind, coverage, meaning = (
                "units",
                "Весь анализ",
                "Количество подтверждённых результатов или сообщений.",
            )
        rows.append(
            {"label": label, "value": value, "coverage": coverage, "meaning": meaning, "format": kind}
        )
    return rows


def methodology(start, end):
    return [
        {"topic": topic, "rule": rule}
        for topic, rule in [
            ("Официальный сезон", f"{start:%d.%m.%Y}–{end:%d.%m.%Y}; дата входа не сдвигает план."),
            (
                "База",
                "Только начальный остаток из актуального факта; объём первой поставки не является знаменателем.",
            ),
            (
                "Замена плана",
                "Точный категорийный норматив по паре вида номенклатуры и вида ассортимента; явный некорректный план не заменяется.",
            ),
            (
                "Предсезон",
                "Сначала дневной факт. Иначе граничная неделя распределяется по календарным дням; известные недели суммируются с отметкой неполноты.",
            ),
            (
                "Три оценки",
                "Предварительный уровень — только выполнение. Коммерческий статус — сезонное наблюдение, выполнение и прогноз. Операционный статус — отдельные доказательства и проверки.",
            ),
            (
                "Наблюдение",
                "От более поздней из дат начала сезона и фактического коммерческого входа. По умолчанию 14 дней; короткий срок требует явного узкосезонного норматива. Дни включительно: первая оценка на дату начала + 13 дней.",
            ),
            (
                "Размеры",
                "Агрегаты без утверждённых порогов дают сигнал проверки. Подтверждённая проблема требует явного отрицательного признака.",
            ),
            (
                "Сопоставимость",
                "Известные суммы с покрытием. Реализация — сумма факта / сумма базы на парном наборе; выполнение — сумма факта / сумма плана на собственном парном наборе.",
            ),
            (
                "Прогноз",
                "Консервативный темп 3–4 завершённых недель; 2 недели только как резерв. Предсезонный темп условен и сам по себе не подтверждает ХИТ.",
            ),
            (
                "Вторая поставка",
                "Подтверждённая партия и условный сценарий раздельны. Продажи между партиями не распределяются и не восстанавливаются из остатков.",
            ),
            (
                "Округление",
                "Физические единицы округлены после расчёта: половины от нуля. Итоги сначала суммируются без округления. Темпы и проценты сохраняют дробную точность.",
            ),
            (
                "Неизвестные данные",
                "Пустое значение не равно нулю или отрицательному признаку. Детальные основания и происхождение доступны в карточке и API.",
            ),
        ]
    ]
