"""Explicit source values only. A corporate range is never an article value."""

import re

from app.shared.excel import fraction, norm, number

FIELDS = {
    "discount": ("Скидка", "Плановая скидка"),
    "markup": ("Наценка", "Markup", "Целевая наценка"),
    "margin": ("Маржа", "Целевая маржа"),
    "price": ("Плановая цена", "Цена"),
    "revenue": ("Плановая выручка", "Выручка"),
    "cost": ("Себестоимость",),
    "gmroi": ("Целевой GMROI",),
    "cover_weeks": ("Норматив покрытия, недель",),
    "turnover": ("Целевая оборачиваемость",),
    "max_discount": ("Утверждённый предел скидки",),
    "observation_days": ("Утверждённый срок наблюдения, дней",),
    "review_days": ("Утверждённый срок проверки цены, дней",),
}
LABELS = {
    "discount": "Скидка",
    "markup": "Наценка",
    "margin": "Маржа",
    "price": "Цена",
    "revenue": "Выручка",
    "cost": "Себестоимость",
    "gmroi": "Доходность товарного капитала",
    "cover_weeks": "Покрытие, недель",
    "turnover": "Оборачиваемость",
    "max_discount": "Предел скидки",
    "observation_days": "Срок наблюдения, дней",
    "review_days": "Срок проверки цены, дней",
}


def read(table, row, ri):
    result = {}
    for key, aliases in FIELDS.items():
        ci = table.col(*aliases)
        value = table.get(row, *aliases)
        parsed = (
            fraction(value, row[ci].fmt)
            if ci is not None and key in ("discount", "margin", "max_discount")
            else number(value)
        )
        if ci is not None:
            result[key] = {
                "value": parsed,
                "raw": str(value) if value is not None else None,
                "sheet": table.sheet,
                "row": ri,
                "column": ci + 1,
                "header": table.paths[ci],
            }
    return result


def resolve(article, category, month):
    result = {}
    for key in FIELDS:
        for source, record in (("Поартикульный план", article), ("Категорийный план", category)):
            if not record:
                continue
            monthly = record.get("monthly_" + key, {})
            value = monthly.get(month)
            detail = record.get("norms", {}).get(key, {})
            monthly_detail = record.get("monthly_sources", {}).get(f"{key}:{month}", {})
            if value is None and monthly_detail.get("raw"):
                result[key] = {**monthly_detail, "value": None, "source": source, "invalid": True}
                break
            if value is not None:
                detail = {"value": value, **record.get("monthly_sources", {}).get(f"{key}:{month}", {})}
            elif detail.get("value") is None:
                # Malformed explicit norms block fallback; an empty cell does not.
                if detail.get("raw"):
                    result[key] = {**detail, "source": source, "invalid": True}
                    break
                continue
            result[key] = {**detail, "source": source}
            value = result[key].get("value")
            if value is not None and (
                value < 0
                or (key in ("discount", "margin", "max_discount") and value > 1)
                or (
                    key in ("observation_days", "review_days")
                    and (value <= 0 or not float(value).is_integer())
                )
            ):
                result[key].update(value=None, invalid=True)
            break
    return result


def strategy(fact, plan):
    fields = [
        ("Тип сезонности", (plan or {}).get("type", "")),
        ("Вид ассортимента", fact.get("assortment", "")),
        ("Линия", fact.get("line", "")),
        ("Тип сезонности FACT", fact.get("type", "")),
    ]
    for field, value in fields:
        text = norm(value)
        if re.search(r"\bnos\b|постоянн.*налич|\bcore\b", text):
            return {
                "kind": "nos",
                "label": "Постоянное наличие (базовый ассортимент)",
                "field": field,
                "value": value,
                "limitation": "Для постоянного наличия нужны покрытие и оборачиваемость. Правило перевода этих показателей в пять статусов не задано; сезонный статус не применяется.",
            }
    return {
        "kind": "seasonal",
        "label": "Сезонная стратегия",
        "field": fields[0][0],
        "value": fields[0][1],
        "limitation": None,
    }


def display(resolved):
    return "; ".join(
        f"{LABELS[k]}: {format_value(k, v.get('value'))} ({v['source']}, {v.get('sheet', '')}, строка {v.get('row', '?')})"
        for k, v in resolved.items()
    )


def format_value(key, value):
    if value is None:
        return "не определено"
    return f"{value * 100:.2f}%" if key in ("discount", "margin", "max_discount") else f"{value:.2f}"


def comparisons(fact, resolved, metrics):
    rows = []
    for key in ("discount", "price", "markup", "margin", "gmroi", "cover_weeks", "turnover"):
        detail = resolved.get(key, {})
        target = detail.get("value")
        actual = (
            metrics.get("cover")
            if key == "cover_weeks"
            else metrics.get("gmroi")
            if key == "gmroi"
            else fact.get(key)
        )
        comparable = key in ("discount", "price", "cover_weeks")
        rows.append(
            {
                "label": LABELS[key],
                "actual_text": format_value(key, actual),
                "norm_text": format_value(key, target),
                "difference_text": format_value(key, actual - target)
                if comparable and actual is not None and target is not None
                else "не рассчитано",
                "actual": actual,
                "target": target,
                "difference": actual - target
                if comparable and actual is not None and target is not None
                else None,
                "source": detail.get("source"),
                "comment": "Сопоставлены значения в одной единице; отклонение само по себе не разрешает ценовое действие."
                if comparable
                else "Для оценки выполнения экономической нормы нужно подтвердить одинаковый период и состав товаров.",
            }
        )
    return rows


def cover_interpretation(fact, metrics, resolved, selected_strategy):
    if selected_strategy["kind"] != "nos":
        return (
            "Покрытие сопоставляется с оставшимся нормативным сроком только при наличии однозначного срока."
        )
    target = resolved.get("cover_weeks", {}).get("value")
    cover = metrics.get("cover")
    if target is None or cover is None:
        return "Постоянное наличие: нет фактического покрытия или индивидуального норматива; возраст партии не определяет избыточность."
    return f"Постоянное наличие: покрытие {cover:.2f} нед., норматив {target:.2f} нед.; отклонение {cover - target:+.2f} нед. Для итогового статуса нужны правило допустимого отклонения и оборачиваемость."
