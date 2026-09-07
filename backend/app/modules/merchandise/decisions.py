"""Deterministic decisions with evidence, not invented thresholds for qualitative rules."""

from datetime import date, timedelta

from app.modules.merchandise.metrics import ratio

STATUSES = ["ХИТ", "В ПЛАНЕ", "РИСК", "АУТСАЙДЕР", "НЕДОСТАТОЧНО ДАННЫХ"]
OPERATION_ORDER = [
    ("representation_ok", "представленность"),
    ("sizes_ok", "ходовые размеры"),
    ("distribution_ok", "распределение"),
    ("replenishment_ok", "подсортировка"),
    ("stop_checked", "остановка подсортировки"),
    ("stores_checked", "сокращение числа магазинов"),
    ("warehouse_checked", "перераспределение через склад"),
    ("channel_checked", "смена канала"),
]


def second_wave(f, m, p, control, end):
    if not p or not (p.get("second_date") or p.get("second_qty")):
        return None
    delivery = p.get("second_date")
    base = m["base"]
    target = base * 0.7 if base is not None and base > 0 else None
    actual = f.get("second_actual") or delivery
    before = actual is not None and control < actual
    first = f.get("first_batch_sales")
    if first is None and before:
        # Skill permits all cumulative sales only before second arrival.
        first = f.get("sales_total")
        if first is None and m["season_fact"] is not None and m["preseason"] is not None:
            first = m["season_fact"] + m["preseason"]
    left = max(0, (delivery - control).days / 7) if delivery else None
    gap = max(target - first, 0) if target is not None and first is not None else None
    required = 0 if gap == 0 else ratio(gap, left)
    forecast = (
        first + m["pace"] * left if first is not None and m["pace"] is not None and left is not None else None
    )
    comment = []
    if first is None:
        comment.append(
            "Продажи первой партии не определены: после поступления второй партии нужны отдельные партийные данные."
        )
    if delivery is None or p.get("second_qty") is None:
        comment.append("Отсутствуют дата или объём второй поставки.")
    risk = forecast is not None and target is not None and forecast < target
    outside = delivery is not None and delivery > end
    capacity = (
        (f.get("stock") + p["second_qty"] <= m["pace"] * max(0, (end - delivery).days / 7))
        if all(v is not None for v in (f.get("stock"), p.get("second_qty"), m.get("pace"), delivery))
        else None
    )
    if outside:
        decision = "изменить канал входа"
        comment.append("Поставка выходит за официальное сезонное окно; ввод в сезонную матрицу не обоснован.")
    elif risk:
        decision = "удержать у поставщика"
        comment.append(
            "Прогноз ниже цели 70%; согласовать частичный забор, перенос или сокращение до подтверждения партии."
        )
    elif capacity is False:
        decision = "принять частично"
        comment.append(
            "Полный объём не покрывается прогнозным спросом до конца сезонного окна; количество требует подтверждения."
        )
    elif forecast is not None and all(
        f.get(k) is True for k in ("economics_ok", "capacity_ok", "channel_ok")
    ):
        decision = (
            "ускорить забор"
            if m.get("cover") is not None and left is not None and m["cover"] < left
            else "принять полностью"
        )
        comment.append("Цель, экономика, запас и канал подтверждены входными данными.")
    else:
        decision = "согласовать условия поставки"
        comment.append(
            "Нужны подтверждение экономики, допустимого запаса и канала; автоматический забор не назначен."
        )
    return {
        "article": f["article"],
        "base": base,
        "first_sales": first,
        "first_st": ratio(first, base),
        "target70": target,
        "remaining70": gap,
        "second_date": delivery.isoformat() if delivery else None,
        "second_qty": p.get("second_qty"),
        "weeks": left,
        "required": required,
        "pace": m["pace"],
        "pace_ratio": ratio(m["pace"], required),
        "forecast": forecast,
        "forecast_st": ratio(forecast, base),
        "gap": forecast - target if forecast is not None and target is not None else None,
        "decision": decision,
        "comment": " ".join(comment),
        "risk": risk or outside or capacity is False,
    }


def operational_evidence(f, m, p):
    evidence = {key: f.get(key) for key, _ in OPERATION_ORDER}
    if (
        evidence["representation_ok"] is None
        and f.get("planned_stores") is not None
        and f.get("effective_stores") is not None
    ):
        evidence["representation_ok"] = f["effective_stores"] >= f["planned_stores"]
    if f.get("stores") == 0 and (f.get("warehouse") or 0) > 0:
        evidence["representation_ok"] = False
    # A ratio alone does not prove that specific key sizes are available.
    if f.get("avg_sizes") == 0 and (f.get("stock") or 0) > 0:
        evidence["sizes_ok"] = False
    return evidence


def status(m, operations, second, control, start, p, critical=False):
    min_days = 7 if p and "узкосезон" in p["type"].lower() else 14
    observed = m["age"]
    if critical or control < start or m["execution"] is None or observed is None or observed < min_days:
        return "НЕДОСТАТОЧНО ДАННЫХ"
    execution = m["execution"]
    base = (
        "ХИТ"
        if execution >= 1.15
        else "В ПЛАНЕ"
        if execution >= 0.85
        else "РИСК"
        if execution >= 0.70
        else "АУТСАЙДЕР"
    )
    if m["pace"] is None and control < date.fromisoformat(m["deadline"]):
        return "НЕДОСТАТОЧНО ДАННЫХ"
    risk = (
        (m["forecast"] is not None and m["season_plan"] is not None and m["forecast"] < m["season_plan"])
        or any(v is False for v in operations.values())
        or bool(second and second["risk"])
    )
    if base == "ХИТ":
        confirmations = (
            m["forecast"] is not None
            and m["forecast"] >= m["season_plan"]
            and m["pace"] is not None
            and m["pace"] > 0
            and m.get("season_pace_weeks", 0) >= 2
            and operations["representation_ok"] is True
            and operations["sizes_ok"] is True
        )
        if not confirmations:
            base = "В ПЛАНЕ"
    if risk and base in ("ХИТ", "В ПЛАНЕ"):
        return "РИСК"
    if base == "АУТСАЙДЕР":
        primary_days = 14 if min_days == 7 else 21
        if observed < primary_days:
            return "РИСК"
        # Do not diagnose weak demand solely from operational unavailability.
        if any(operations[k] is not True for k in ("representation_ok", "sizes_ok", "distribution_ok")):
            return "РИСК"
        if m["forecast"] is None or m["forecast"] >= m["season_plan"]:
            return "РИСК"
    return base


def diagnose(f, m, p, operations, second, s):
    if s == "НЕДОСТАТОЧНО ДАННЫХ":
        return "недостаточно данных", None
    causes = []
    for key, label in [
        ("representation_ok", "недостаточная представленность"),
        ("sizes_ok", "выбитые размеры"),
        ("distribution_ok", "ошибочное распределение"),
        ("replenishment_ok", "недостаточная подсортировка"),
    ]:
        if operations[key] is False:
            causes.append(label)
    if second and second["risk"]:
        causes.append("риск второй поставки")
    if f.get("store_date") and p and p.get("entry") and f["store_date"] > p["entry"]:
        causes.append("поздняя поставка")
    if (
        f.get("warehouse")
        and m.get("pace") is not None
        and m["pace"] > 0
        and (f["warehouse"] / m["pace"]) / (365.25 / 12 / 7) > 4.5
    ):
        causes.append("высокий складской запас")
    if m["cover"] is not None and m["cover"] > m["weeks_remaining"]:
        causes.append("избыточная глубина")
    if f.get("seasonality_confirmed") is True:
        causes.append("сезонность")
    if not causes:
        causes.append(
            "высокий спрос"
            if s == "ХИТ"
            else "нормальная динамика"
            if s == "В ПЛАНЕ"
            else "слабый спрос"
            if all(operations[k] is True for k in ("representation_ok", "sizes_ok", "distribution_ok"))
            else "недостаточно данных"
        )
    return causes[0], causes[1] if len(causes) > 1 else None


def pricing(f, m, p, s, operations, second, control):
    decision, change, reason = (
        "держать цену",
        "Без изменения",
        "Оснований для изменения цены не подтверждено.",
    )
    review = control + timedelta(days=7)
    checks = [
        {"step": i + 1, "check": label, "confirmed": operations[key]}
        for i, (key, label) in enumerate(OPERATION_ORDER)
    ]
    if s == "НЕДОСТАТОЧНО ДАННЫХ":
        decision, reason = (
            "проверить данные",
            "Недостаточный срок наблюдения или данные для ценового решения.",
        )
    elif f.get("price") is None or f.get("discount") is None:
        decision, reason = "проверить данные", "Отсутствует текущая цена или скидка."
    elif s == "ХИТ":
        if (
            all(operations[k] is True for k in ("representation_ok", "sizes_ok", "distribution_ok"))
            and not (second and second["risk"])
            and f.get("price_room") is True
            and m["forecast"] is not None
            and m["forecast"] >= m["season_plan"]
            and m["cover"] is not None
            and m["cover"] <= m["weeks_remaining"]
        ):
            decision = "уменьшить скидку" if f["discount"] >= 0.03 else "повысить цену"
            change = (
                "Уменьшить скидку на 3–5 п.п."
                if decision == "уменьшить скидку"
                else "Тест повышения цены на 3–5%"
            )
            reason = "Устойчивый сезонный спрос, прогноз, размеры, представленность и ценовой потенциал подтверждены."
    elif s in ("РИСК", "АУТСАЙДЕР"):
        first = next(((key, label) for key, label in OPERATION_ORDER if operations[key] is not True), None)
        if first:
            decision, reason = (
                "наблюдать",
                f"До цены проверить: {first[1]}. Операционные условия не подтверждены.",
            )
        elif f.get("repricing_date") and (control - f["repricing_date"]).days < 7:
            decision, reason = "наблюдать", "После последней переоценки прошло меньше 7 дней."
        elif f.get("repricing_date") and f.get("price_effect") is not True:
            decision, reason = (
                "наблюдать",
                "Эффект предыдущей переоценки не подтверждён. Проверить остановку подсортировки, часть сети и другой канал.",
            )
        elif (
            m["forecast"] is not None
            and m["forecast"] < m["season_plan"]
            and m["cover"] is not None
            and m["cover"] > m["weeks_remaining"]
        ):
            stage = f.get("repricing_stage", "").lower()
            lo, hi = (
                (0.10, 0.15) if stage == "средняя" else (0.15, 0.20) if stage == "сильная" else (0.05, 0.10)
            )
            cap = (
                0.60
                if p and "узкосезон" in p["type"].lower() and "верхн" in f["category"].lower()
                else 0.50
                if s == "АУТСАЙДЕР"
                else 0.40
            )
            if f["discount"] >= cap:
                decision, reason = (
                    "держать цену",
                    "Достигнут предел скидки для текущего режима. Согласовать вывод или другой канал.",
                )
            else:
                decision = "снизить цену"
                change = f"Добавить {min(lo, cap - f['discount']) * 100:.0f}–{min(hi, cap - f['discount']) * 100:.0f} п.п.; итоговая скидка не выше {cap * 100:.0f}%"
                reason = "Операционные причины проверены; прогноз подтверждает недобор при избыточном запасе."
    return {
        "article": f["article"],
        "status": s,
        "price": f.get("price"),
        "discount": f.get("discount"),
        "markup": f.get("markup"),
        "margin": f.get("margin"),
        "decision": decision,
        "change": change,
        "reason": reason,
        "review_date": review.isoformat(),
        "checks": checks,
    }


def recommend(f, m, p, s, causes, operations, price, second, control):
    owner = "Коммерческое планирование"
    days_to_check = 7 - control.weekday()  # Next Monday, always future.
    review = control + timedelta(days=days_to_check)
    if s == "НЕДОСТАТОЧНО ДАННЫХ":
        action = "Уточнить отсутствующие данные и повторить оценку после достаточного срока наблюдения."
        if m["age"] is not None and m["age"] < 14:
            review = control + timedelta(days=max(1, 14 - m["age"]))
    elif s in ("РИСК", "АУТСАЙДЕР"):
        actions = {
            "representation_ok": "Сверить план представленности и фактические магазины; обеспечить вход со склада в сильные точки.",
            "sizes_ok": "Проверить ходовые размеры; восстановить рабочий ряд складской подсортировкой.",
            "distribution_ok": "Сопоставить продажи и остатки Р1–Р4; ограничить загрузку слабых точек.",
            "replenishment_ok": "Проверить резерв и отгрузки со склада в точки с подтверждённым спросом.",
            "stop_checked": "Оценить остановку дополнительной подсортировки медленных точек.",
            "stores_checked": "Оценить сокращение числа магазинов с медленным запасом.",
            "warehouse_checked": "Оценить централизованный возврат и сбор размерных рядов через склад.",
            "channel_checked": "Согласовать канал реализации: интернет-магазин, аутлет или маркетплейс с учётом линии товара.",
        }
        missing = next((key for key, _ in OPERATION_ORDER if operations[key] is not True), None)
        action = actions[missing] if missing else price["change"] + ". " + price["reason"]
        if missing == "sizes_ok":
            owner = "Категорийный менеджер / Розница"
        if price["decision"] == "снизить цену":
            review = date.fromisoformat(price["review_date"])
    elif s == "ХИТ":
        action = (
            price["change"] + ". Проверить возможность повтора и складской резерв для подтверждённого спроса."
        )
        review = date.fromisoformat(price["review_date"])
    else:
        action = "Сохранить цену и рабочую подсортировку; на следующем срезе сверить выполнение плана и прогноз к сроку."
    if "signature" in f.get("line", "").lower():
        action += " Для уникальной линии ранний выход на маркетплейсы исключён; приоритет Р1, Р2 и интернет-магазин."
    if "edition" in f.get("line", "").lower():
        action += " Пилотную линию расширять только после подтверждения спроса."
    if second and second["risk"]:
        action += " " + second["decision"].capitalize() + ": " + second["comment"]
        if second["second_date"]:
            confirm = date.fromisoformat(second["second_date"]) - timedelta(days=1)
            review = min(review, confirm) if confirm > control else control + timedelta(days=1)
        owner += " / Закупки / ВЭД / Логистика"
    if p and "узкосезон" in p["type"].lower() and m["weeks_remaining"] < 1:
        review = control + timedelta(days=1)
    happening = (
        f"Выполнение плана {m['execution'] * 100:.1f}%."
        if m["execution"] is not None
        else "Надёжная оценка выполнения плана пока невозможна."
    )
    return {
        "priority": "Критично"
        if second and second["risk"] and second.get("weeks") is not None and second["weeks"] < 1
        else "Высокий"
        if s in ("РИСК", "АУТСАЙДЕР")
        else "Наблюдение"
        if s == "НЕДОСТАТОЧНО ДАННЫХ"
        else "Средний",
        "article": f["article"],
        "problem": causes[0],
        "action": action,
        "owner": owner,
        "review_date": review.isoformat(),
        "expected": "Подтвердить спрос, доступность и выполнение целевой реализации без необоснованной уценки.",
        "recommendation": f"{happening} Причина: {causes[0]}. {action} Проверка {review:%d.%m.%Y}.",
    }
