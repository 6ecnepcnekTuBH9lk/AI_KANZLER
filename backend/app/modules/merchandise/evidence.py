"""Aggregate evidence never identifies an unobserved size or store."""

LABELS = {
    "execution": "Выполнение плана",
    "forecast": "Прогноз",
    "season_plan": "Цель сезона, ед.",
    "pace": "Устойчивый темп",
    "age": "Возраст, дней",
    "stock": "Остаток",
    "cover": "Покрытие, недель",
    "weeks_remaining": "Недель до срока",
    "base": "Начальный остаток",
    "first_sales": "Продажи до второй поставки",
    "second_date": "Дата второй поставки",
    "target70": "Цель 70%, ед.",
    "entry": "Утверждённая дата входа",
    "warehouse_known": "Известная часть складского остатка",
    "planned_stores": "План магазинов",
}


def size_state(f):
    fields = []
    confirmed = f.get("sizes_ok") is False
    for key in ("broken_ratio", "broken_stores"):
        if f.get(key) is not None and f[key] > 0:
            fields.append(key)
    if f.get("size_availability") is not None and 0 <= f["size_availability"] < 1:
        fields.append("size_availability")
    if f.get("avg_sizes") is not None and f.get("sizes") is not None and 0 <= f["avg_sizes"] < f["sizes"]:
        fields += ["avg_sizes", "sizes"]
    known = [
        k
        for k in ("sizes", "avg_sizes", "size_availability", "broken_ratio", "broken_stores", "sizes_ok")
        if f.get(k) is not None
    ]
    return {
        "state": "Подтверждённая проблема"
        if confirmed
        else "Требует проверки"
        if fields
        else "Признаков проблемы нет"
        if f.get("sizes_ok") is True
        else "Нет данных для проверки",
        "problem": confirmed,
        "signal": bool(fields),
        "fields": (["sizes_ok"] if confirmed else []) + fields,
        "known_fields": known,
        "core_sizes_confirmed": f.get("sizes_ok") is True and not fields,
        "limitation": "Агрегаты не определяют конкретный отсутствующий размер или магазин; ходовые размеры требуют отдельного подтверждения.",
    }


def diagnose(f, m, p, operations, second, status):
    items = []
    missing = []

    def add(label, rule, fields, source=None):
        inputs = []
        for key in fields:
            if source == "Расчёт":
                inputs.append({"field": key, "value": m.get(key), "source": source})
            else:
                inputs.append(
                    {
                        "field": key,
                        "value": f.get(key),
                        **f.get("provenance", {}).get(
                            key, {"source": "Факт продаж", "row": f.get("source_row")}
                        ),
                    }
                )
        items.append({"diagnosis": label, "rule": rule, "inputs": inputs})

    if operations.get("representation_ok") is False:
        add(
            "недостаточная представленность",
            "Skill §30,41: представленность до цены",
            [
                k
                for k in (
                    "representation_ok",
                    "planned_stores",
                    "effective_stores",
                    "stores",
                    "warehouse",
                    "warehouse_known",
                )
                if f.get(k) is not None
            ],
        )
    sizes = size_state(f)
    if sizes["problem"]:
        add("проблема размерной доступности", "Skill §29: агрегатная размерная доступность", sizes["fields"])
    elif sizes["signal"]:
        add(
            "размерная доступность требует проверки",
            "Агрегатный сигнал без утверждённого порога",
            sizes["fields"],
        )
    if operations.get("distribution_ok") is False:
        add("ошибочное распределение", "Skill §30,40: подтверждённое распределение", ["distribution_ok"])
    if f.get("warehouse_skew_confirmed") is True or (
        f.get("stores") == 0 and (f.get("warehouse") or f.get("warehouse_known") or 0) > 0
    ):
        add(
            "складской перекос",
            "Skill §30: склад без представленности / явное подтверждение",
            [
                k
                for k in ("stores", "warehouse", "warehouse_known", "warehouse_skew_confirmed")
                if f.get(k) is not None
            ],
        )
    for field, label in (
        ("replenishment_needed", "нужна подсортировка"),
        ("stop_needed", "нужна остановка подсортировки"),
        ("stores_reduction_needed", "нужно сократить количество магазинов"),
        ("warehouse_transfer_needed", "нужно перераспределение через склад"),
        ("alternate_channel_needed", "нужен альтернативный канал"),
    ):
        if f.get(field) is True:
            add(label, "Skill §40: подтверждённая операционная потребность", [field])
    if second and second["risk"]:
        items.append(
            {
                "diagnosis": "риск второй поставки",
                "rule": "Skill §31: база FACT × 70%",
                "inputs": [
                    {"field": k, "value": second.get(k), "source": "Расчёт второй поставки"}
                    for k in ("base", "first_sales", "second_date", "pace", "forecast", "target70")
                ],
            }
        )
    if f.get("store_date") and p and p.get("entry") and f["store_date"] > p["entry"]:
        add("поздняя поставка", "Skill §18: фактический вход позже утверждённого", ["store_date"])
        items[-1]["inputs"].append(
            {
                "field": "entry",
                "value": p["entry"].isoformat(),
                "source": "Поартикульный план",
                "row": p.get("source_row"),
            }
        )
    if (
        m.get("strategy", {}).get("kind") != "nos"
        and m.get("cover") is not None
        and m.get("weeks_remaining") is not None
        and m["cover"] > m["weeks_remaining"]
    ):
        add(
            "избыточная глубина",
            "Skill §25: покрытие превышает оставшееся время",
            ["stock", "pace", "cover", "weeks_remaining"],
            "Расчёт",
        )
    if f.get("seasonality_confirmed") is True:
        add("сезонность", "Skill §40: подтверждение источника", ["seasonality_confirmed"])
    for k, label in (
        ("representation_ok", "представленность"),
        ("sizes_ok", "ходовые размеры"),
        ("distribution_ok", "распределение"),
    ):
        if operations.get(k) is not True:
            missing.append("Не подтверждено устранение/отсутствие проблемы: " + label)
    if f.get("distribution") is not None and f.get("distribution_ok") is None:
        missing.append(
            "Для коэффициента распределения нет утверждённого порога; сам коэффициент не доказывает ошибку."
        )
    if not sizes["core_sizes_confirmed"]:
        missing.append(sizes["limitation"])
    if m.get("deadline") is None:
        missing.append("Нет однозначного нормативного срока для прогноза и требуемого темпа.")
    if m.get("strategy", {}).get("limitation"):
        missing.append(m["strategy"]["limitation"])
    if not items:
        label = (
            "высокий спрос"
            if status == "ХИТ"
            else "нормальная динамика"
            if status == "В ПЛАНЕ"
            else "слабый спрос"
            if status == "АУТСАЙДЕР"
            and all(operations.get(k) is True for k in ("representation_ok", "sizes_ok", "distribution_ok"))
            else "недостаточно данных"
        )
        add(
            label,
            "Skill §34–40: итог оценки и достаточность доказательств",
            ["execution", "forecast", "season_plan", "pace", "age"],
            "Расчёт",
        )
    # Dates are converted here so API persistence and JSON fixtures share one representation.
    for item in items:
        for value in item["inputs"]:
            value["label"] = value.get("header") or LABELS.get(value["field"], "Входной показатель")
            if hasattr(value["value"], "isoformat"):
                value["value"] = value["value"].isoformat()
    return {
        "primary": items[0]["diagnosis"],
        "secondary": items[1]["diagnosis"] if len(items) > 1 else None,
        "evidence": items,
        "missing_evidence": missing,
        "sizes": sizes,
    }


def display(diagnosis):
    return "; ".join(
        item["diagnosis"]
        + ": "
        + ", ".join(
            f"{v['label']}={v['value']} ({v.get('source', '')}, строка {v.get('row', '—')})"
            for v in item["inputs"]
        )
        for item in diagnosis["evidence"]
    )
