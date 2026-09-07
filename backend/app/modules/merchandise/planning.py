from calendar import monthrange
from datetime import date, timedelta


def days(start, end):
    for i in range(max(0, (end - start).days + 1)):
        yield start + timedelta(days=i)


def season_months(start, end):
    return sorted({(d.year, d.month) for d in days(start, end)})


def build_plan(plan, category, base, start, end):
    """Skill §16. No first-batch quantity is accepted by this function."""
    warnings = []
    if plan is None:
        return None, ["Нет утверждённого поартикульного плана."]
    target = plan["target"]
    if target is None and category:
        target = category["target"]
        if target is not None:
            warnings.append("Целевой процент взят из точного категорийного норматива.")
    if target is None or not 0 < target <= 1:
        return None, ["Отсутствует или некорректен целевой процент реализации сезона."]
    if base is None or base <= 0:
        return None, ["Для расчёта плана нужен положительный начальный остаток."]
    source = plan
    official = plan.get("weekly_plan", {})
    if official:
        points = sorted(
            (min(d + timedelta(days=6), end), p)
            for d, p in official.items()
            if d <= end and d + timedelta(days=6) >= start
        )
        expected = weekly_ends(start, end)
        if [d for d, p in points] != expected or any(p is None or p < 0 for d, p in points):
            return None, [
                "Официальная недельная кривая неполна; автоматическая замена месячной не выполнена."
            ]
        if abs(points[-1][1] - target) > 1e-6 or any(
            points[i][1] < points[i - 1][1] for i in range(1, len(points))
        ):
            return None, ["Накопительная недельная кривая противоречит целевому проценту."]
        daily, previous, previous_date = {}, 0, start
        for week_end, cumulative in points:
            interval = list(days(previous_date, week_end))
            for d in interval:
                daily[d] = (cumulative - previous) / len(interval)
            previous, previous_date = cumulative, week_end + timedelta(days=1)
        warnings.append("Внутри официальной недели план распределён равномерно для контрольной даты.")
    else:
        if not source["months"] and category:
            source = category
            warnings.append("Месячная форма взята из точного категорийного норматива.")
        month_keys = season_months(start, end)
        values = [source["months"].get(m) for y, m in month_keys]
        if not values or any(v is None or v < 0 for v in values) or sum(values) <= 0:
            return None, warnings + ["Отсутствует, неполна или некорректна месячная форма плана."]
        if source["month_mode"] == "pct":
            if abs(sum(values) - target) > 1e-6:
                return None, warnings + [
                    "Сумма месячных процентов не равна целевому проценту; требуется согласование плана."
                ]
            shares = values
        else:
            shares = [target * v / sum(values) for v in values]
        daily = {}
        for (year, month), share in zip(month_keys, shares):
            interval = list(
                days(
                    max(start, date(year, month, 1)), min(end, date(year, month, monthrange(year, month)[1]))
                )
            )
            for d in interval:
                daily[d] = share / len(interval)
    cumulative = 0.0
    deadline = plan.get("deadline")
    if deadline and deadline < end and any(v > 0 for d, v in daily.items() if d > deadline):
        warnings.append(
            "План содержит продажи после нормативного срока реализации. Кривая сохранена из источника; "
            "срок прогноза не продлён. Требуется согласовать план и срок."
        )
    weekly = []
    for d in days(start, end):
        cumulative += daily[d]
        if d.weekday() == 6 or d == end:
            weekly.append(
                {
                    "week_start": (d - timedelta(days=d.weekday())).isoformat(),
                    "week_end": d.isoformat(),
                    "pct": cumulative,
                }
            )
    return {"target": target, "season_units": base * target, "daily": daily, "weekly": weekly}, warnings


def weekly_ends(start, end):
    return [d for d in days(start, end) if d.weekday() == 6 or d == end]


def plan_at(plan, base, control, start, end):
    if plan is None or control < start:
        return None, None
    pct = sum(v for d, v in plan["daily"].items() if d <= min(control, end))
    return pct, base * pct


def add_months(d, count):
    i = d.year * 12 + d.month - 1 + count
    y, m = divmod(i, 12)
    return date(y, m + 1, min(d.day, monthrange(y, m + 1)[1]))
