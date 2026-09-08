import re
from datetime import timedelta
from statistics import mean

from app.modules.merchandise.planning import add_months, days


def ratio(a, b):
    return a / b if a is not None and b is not None and b > 0 else None


def sales_window(fact, start, control, end):
    qa = []
    stop = min(control, end)
    weekly = fact["weekly"]
    if fact.get("daily"):
        daily = fact["daily"]
        needed = list(days(start, stop))
        official = (
            sum(daily[d] for d in needed)
            if needed and all(d in daily and daily[d] is not None for d in needed)
            else None
        )
        prior = [v for d, v in daily.items() if d < start and d <= control]
        preseason = sum(prior) if prior and all(v is not None for v in prior) else None
        return official, preseason, qa
    if not weekly:
        return None, None, ["Нет недельных или дневных продаж."]
    official = 0.0 if control >= start else None
    prior_values = []
    prior_missing = False
    present = set()
    for week, qty in sorted(weekly.items()):
        if week > control:
            continue
        actual_end = min(week + timedelta(days=6), control)
        denominator = (actual_end - week).days + 1
        seasonal_days = max(0, (min(actual_end, stop) - max(week, start)).days + 1)
        prior_days = max(0, (min(actual_end, start - timedelta(days=1)) - week).days + 1)
        if seasonal_days:
            present.add(week)
            if qty is None:
                official = None
            elif official is not None:
                official += qty * seasonal_days / denominator
                if seasonal_days != denominator:
                    qa.append(
                        "Факт граничной недели распределён пропорционально календарным дням сезонного окна."
                    )
        if prior_days:
            if qty is None:
                prior_missing = True
            else:
                prior_values.append(qty * prior_days / denominator)
                if prior_days != denominator:
                    qa.append("Предсезонный факт оценён пропорциональным распределением граничной недели.")
    if control >= start:
        needed = {d - timedelta(days=d.weekday()) for d in days(start, stop)}
        if not needed.issubset(present):
            official = None
            qa.append("Пропущены недели официального сезона; сезонный факт не рассчитан.")
    if prior_missing:
        qa.append(
            "Предсезонные продажи показаны по известным неделям; пропуски не заменены нулём."
            if prior_values
            else "Предсезонные продажи неизвестны: нет заполненных недель до начала сезона."
        )
    return official, sum(prior_values) if prior_values else None, qa


def pace_metrics(fact, control, start, end):
    qa = []
    stop = min(control, end)
    week = stop - timedelta(days=stop.weekday())
    partial = stop.weekday() != 6

    def week_sales(monday):
        if fact.get("daily"):
            needed = list(days(monday, min(monday + timedelta(days=6), stop)))
            daily = fact["daily"]
            return (
                sum(daily[d] for d in needed)
                if needed and all(daily.get(d) is not None for d in needed)
                else None
            )
        return fact["weekly"].get(monday)

    current = week_sales(week)
    previous = week_sales(week - timedelta(days=7))
    # Skill §22–26: contiguous completed weeks; early demand is explicitly labelled.
    last = week - timedelta(days=7) if partial else week
    values = []
    for i in range(4):
        d = last - timedelta(days=7 * i)
        qty = week_sales(d)
        if qty is None:
            break
        values.append(qty)
    avg2 = mean(values[:2]) if len(values) >= 2 else None
    avg4 = mean(values) if len(values) >= 3 else None
    pace = avg4 if avg4 is not None else avg2
    if len(values) == 2:
        qa.append("Темп основан только на двух завершённых неделях; надёжность ниже.")
    elif len(values) < 2:
        qa.append(
            "Меньше двух завершённых недель с данными; устойчивый темп и линейный прогноз не рассчитаны."
        )
    if any(last - timedelta(days=7 * i) < start for i in range(len(values))):
        qa.append(
            "В оценке темпа есть предсезонные недели. Прогноз условный; этот темп сам по себе не подтверждает ценовую силу."
        )
    if partial:
        qa.append("Текущая неделя неполная; прямое сравнение с полной предыдущей неделей не выполнено.")
    wow = ratio(current, previous) - 1 if not partial and ratio(current, previous) is not None else None
    return {
        "current_week": current,
        "previous_week": previous,
        "avg2": avg2,
        "avg4": avg4,
        "pace": pace,
        "wow": wow,
        "partial_week": partial,
        "pace_weeks": len(values),
        "season_pace_weeks": sum(last - timedelta(days=7 * i) >= start for i in range(len(values))),
    }, qa


def deadline_for(plan, entry, end):
    if plan and plan.get("deadline"):
        return min(end, plan["deadline"])
    if plan and plan.get("term") and plan.get("entry"):
        m = re.fullmatch(r"\s*(\d+)\s*(месяц(?:а|ев)?|дн(?:я|ей)?)\s*", plan["term"].lower())
        if m:
            d = (
                add_months(plan["entry"], int(m[1]))
                if m[2].startswith("месяц")
                else plan["entry"] + timedelta(days=int(m[1]))
            )
            return min(end, d)
    return None


def calculate(fact, plan, trajectory, control, start, end, plan_pct, plan_units):
    qa = []
    official, preseason, notes = sales_window(fact, start, control, end)
    qa += notes
    pace, notes = pace_metrics(fact, control, start, end)
    qa += notes
    entry = fact["store_date"] or fact["sales_date"] or fact["warehouse_date"]
    if not fact["store_date"] and not fact["sales_date"] and fact["warehouse_date"]:
        qa.append("Возраст рассчитан от поступления на склад, дата коммерческого входа неизвестна.")
    age = (control - entry).days if entry else None
    commercial_entry = fact["store_date"] or fact["sales_date"]
    observation_start = max(start, commercial_entry) if commercial_entry else None
    observation_days = max(0, (min(control, end) - observation_start).days + 1) if observation_start else None
    if age is not None and age < 0:
        qa.append("Дата входа позже контрольной даты.")
        age = None
    deadline = deadline_for(plan, entry, end)
    if deadline is None:
        qa.append(
            "Нет однозначного нормативного срока реализации: точка из корпоративного диапазона не выбирается. Требуемый темп и прогноз к сроку не рассчитаны."
        )
    remaining = max(0, (deadline - min(control, end)).days / 7) if deadline else None
    target_units = trajectory["season_units"] if trajectory else None
    required = None
    if target_units is not None and official is not None and remaining is not None:
        gap = max(0, target_units - official)
        required = 0.0 if gap == 0 else gap / remaining if remaining > 0 else None
        if gap and remaining == 0:
            qa.append("Срок реализации завершён, целевой объём не достигнут.")
    forecast = (
        (official + pace["pace"] * remaining)
        if official is not None and pace["pace"] is not None and remaining is not None
        else None
    )
    if deadline and control >= deadline and official is not None:
        forecast = official
    base = fact["base"]
    valid_base = base if base is not None and base > 0 else None
    if base is None or base < 0:
        qa.append("Начальный остаток отсутствует или некорректен.")
    if base == 0 and ((official or 0) > 0 or (preseason or 0) > 0 or (fact["stock"] or 0) > 0):
        qa.append("Начальный остаток равен нулю при наличии продаж или остатка. Проценты не рассчитаны.")
    cover = ratio(fact["stock"], pace["pace"])
    if pace["pace"] == 0:
        qa.append("Покрытие запасом не рассчитывается при нулевом устойчивом темпе.")
    gmroi = (
        ratio(fact.get("gross_profit"), fact.get("avg_cost_stock"))
        if fact.get("gmroi_scope_ok") is True
        else None
    )
    if fact.get("gross_profit") is not None and gmroi is None:
        qa.append(
            "Доходность товарного капитала не рассчитана: нужны средний запас по себестоимости и подтверждение одинакового периода/состава данных."
        )
    return {
        **pace,
        "season_fact": official,
        "preseason": preseason,
        "base": base,
        "stock": fact["stock"],
        "target": trajectory["target"] if trajectory else None,
        "season_plan": target_units,
        "plan_pct": plan_pct,
        "plan_units": plan_units,
        "st": ratio(official, valid_base),
        "execution": ratio(official, plan_units),
        "gap_pp": (
            (official / valid_base - plan_pct) * 100
            if official is not None and valid_base and plan_pct is not None
            else None
        ),
        "gap_units": official - plan_units if official is not None and plan_units is not None else None,
        "required": required,
        "pace_ratio": ratio(pace["pace"], required),
        "cover": cover,
        "forecast": forecast,
        "forecast_st": ratio(forecast, valid_base),
        "age": age,
        "season_observation_start": observation_start.isoformat() if observation_start else None,
        "season_observation_days": observation_days,
        "preseason_estimated": not bool(fact.get("daily")) and preseason is not None,
        "preseason_partial": any("по известным неделям" in n for n in notes + qa),
        "entry": entry.isoformat() if entry else None,
        "deadline": deadline.isoformat() if deadline else None,
        "weeks_remaining": remaining,
        "gmroi": gmroi,
    }, qa
