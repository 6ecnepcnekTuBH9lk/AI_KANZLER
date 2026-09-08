"""Deterministic decisions with evidence, not invented thresholds for qualitative rules."""

from datetime import date, timedelta

from app.modules.merchandise import evidence as diagnostic_evidence
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
    actual = f.get("second_actual")
    before = (actual is not None and control < actual) or (
        actual is None and f.get("second_not_arrived") is True
    )
    first = f.get("first_batch_sales")
    if first is None and before:
        # Skill permits all cumulative sales only before second arrival.
        first = f.get("sales_total")
        if (
            first is None
            and m["season_fact"] is not None
            and m["preseason"] is not None
            and not m.get("preseason_partial")
        ):
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
            "Продажи первой партии не определены: нужны отдельные партийные данные либо подтверждение, что вторая поставка ещё не поступила. Плановая дата не доказывает отсутствие досрочного поступления."
        )
    if delivery is None or p.get("second_qty") is None:
        comment.append("Отсутствуют дата или объём второй поставки.")
    risk = forecast is not None and target is not None and forecast < target
    outside = delivery is not None and delivery > end
    missing = [
        label
        for key, label in (
            ("economics_ok", "экономика"),
            ("capacity_ok", "допустимый запас"),
            ("inventory_months_ok", "запас в месяцах"),
            ("channel_ok", "канал"),
        )
        if f.get(key) is not True
    ]
    if target is None:
        missing.append("положительная база FACT")
    if delivery is None or p.get("second_qty") is None or p.get("second_qty", 0) <= 0:
        missing.append("дата и положительный объём поставки")
    if forecast is None:
        missing.append("продажи первой партии и устойчивый темп")
    if not before:
        missing.append("подтверждение ещё не поступившей поставки")
    if outside:
        decision = "изменить канал входа"
        comment.append("Поставка выходит за официальное сезонное окно; ввод в сезонную матрицу не обоснован.")
    elif risk:
        decision = "удержать у поставщика"
        comment.append(
            "Прогноз ниже цели 70%; согласовать частичный забор, перенос или сокращение до подтверждения партии."
        )
    elif not missing and forecast >= target:
        decision = (
            "ускорить забор"
            if m.get("cover") is not None and left is not None and m["cover"] < left
            else "принять полностью"
        )
        comment.append("Цель, экономика, запас и канал подтверждены входными данными.")
    else:
        decision = "согласовать условия поставки"
        comment.append(
            "Недостающие условия: "
            + ", ".join(missing)
            + ". Количество частичного забора не рассчитывается без экономической модели."
        )
    scenario_sales = f.get("sales_total") if first is None and delivery and control < delivery else None
    scenario_forecast = (
        scenario_sales + m["pace"] * left
        if scenario_sales is not None and m.get("pace") is not None and left is not None
        else None
    )
    if scenario_forecast is not None:
        comment.append(
            "Отдельный условный сценарий предполагает отсутствие досрочного поступления второй партии; не включён в подтверждённый риск и статус."
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
        "completed_weeks": m.get("pace_weeks", 0),
        "missing_conditions": missing,
        "scenario_forecast": scenario_forecast,
        "scenario_risk": scenario_forecast is not None and target is not None and scenario_forecast < target,
        "required": required,
        "pace": m["pace"],
        "pace_ratio": ratio(m["pace"], required),
        "forecast": forecast,
        "forecast_st": ratio(forecast, base),
        "gap": forecast - target if forecast is not None and target is not None else None,
        "decision": decision,
        "comment": " ".join(comment),
        "risk": risk
        or outside
        or any(
            f.get(k) is False for k in ("economics_ok", "capacity_ok", "inventory_months_ok", "channel_ok")
        ),
    }


def operational_evidence(f, m, p):
    evidence = {key: f.get(key) for key, _ in OPERATION_ORDER}
    if (
        evidence["representation_ok"] is None
        and f.get("planned_stores") is not None
        and f.get("effective_stores") is not None
    ):
        evidence["representation_ok"] = f["effective_stores"] >= f["planned_stores"]
    if f.get("stores") == 0 and (f.get("warehouse") or f.get("warehouse_known") or 0) > 0:
        evidence["representation_ok"] = False
    # A ratio alone does not prove that specific key sizes are available.
    if diagnostic_evidence.size_state(f)["problem"]:
        evidence["sizes_ok"] = False
    for need, check in (
        ("replenishment_needed", "replenishment_ok"),
        ("stop_needed", "stop_checked"),
        ("stores_reduction_needed", "stores_checked"),
        ("warehouse_transfer_needed", "warehouse_checked"),
        ("alternate_channel_needed", "channel_checked"),
    ):
        if f.get(need) is True:
            evidence[check] = False
    return evidence


def status(m, operations, second, control, start, p, critical=False):
    if m.get("strategy", {}).get("kind") == "nos":
        return "НЕДОСТАТОЧНО ДАННЫХ"
    min_days = observation_rule(m, p)["minimum_days"]
    observed = m.get("season_observation_days")
    if (
        critical
        or control < start
        or m["execution"] is None
        or observed is None
        or min_days is None
        or observed < min_days
    ):
        return "НЕДОСТАТОЧНО ДАННЫХ"
    base = preliminary_band(m["execution"])
    if not m.get("deadline") or (m["pace"] is None and control < date.fromisoformat(m["deadline"])):
        return "НЕДОСТАТОЧНО ДАННЫХ"
    risk = (
        m["forecast"] is not None and m["season_plan"] is not None and m["forecast"] < m["season_plan"]
    ) or (
        m.get("cover") is not None
        and m.get("weeks_remaining") is not None
        and m["cover"] > m["weeks_remaining"]
    )
    if base == "ХИТ":
        confirmations = (
            m["forecast"] is not None
            and m["forecast"] > m["season_plan"]
            and m["pace"] is not None
            and m["pace"] > 0
            and m.get("season_pace_weeks", 0) >= 2
        )
        if not confirmations:
            base = "В ПЛАНЕ"
    if risk and base in ("ХИТ", "В ПЛАНЕ"):
        return "РИСК"
    if base == "АУТСАЙДЕР" and (m["forecast"] is None or m["forecast"] >= m["season_plan"]):
        return "РИСК"
    return base


def preliminary_band(execution):
    if execution is None:
        return None
    return (
        "ХИТ"
        if execution >= 1.15
        else "В ПЛАНЕ"
        if execution >= 0.85
        else "РИСК"
        if execution >= 0.70
        else "АУТСАЙДЕР"
    )


def observation_rule(m, p):
    explicit = m.get("norms", {}).get("observation_days", {})
    narrow = "узкосезон" in (p or {}).get("type", "").lower()
    minimum = explicit.get("value")
    if minimum is not None and not narrow:
        minimum = max(14, minimum)
    if minimum is None and not explicit.get("invalid") and not narrow:
        minimum = 14
    return {
        "minimum_days": minimum,
        "source": explicit.get("source")
        if explicit.get("value") is not None
        else "Skill §33 / RULES §14.3"
        if minimum
        else None,
        "explicit": explicit,
    }


def commercial_context(m, p, control):
    rule = observation_rule(m, p)
    start = m.get("season_observation_start")
    review = (
        date.fromisoformat(start) + timedelta(days=rule["minimum_days"] - 1)
        if start and rule["minimum_days"]
        else None
    )
    return {
        "preliminary_band": preliminary_band(m["execution"]),
        "observation_rule": rule,
        "earliest_status_review_date": review.isoformat() if review else None,
    }


def status_reason(m, p, s, critical=False):
    minimum = observation_rule(m, p)["minimum_days"]
    observed = m.get("season_observation_days")
    if critical:
        return "Существенный конфликт коммерческих данных."
    if m.get("strategy", {}).get("kind") == "nos":
        return "Для постоянного наличия не утверждено правило коммерческих статусов."
    if observed is None:
        return "Нет фактической даты коммерческого входа для сезонного наблюдения."
    if minimum is None:
        return "Нет однозначного утверждённого срока наблюдения."
    if observed < minimum:
        return f"Только {observed} дней сезонного наблюдения; требуется {minimum:g}."
    if s == "НЕДОСТАТОЧНО ДАННЫХ":
        return "Недостаточно данных плана, факта, срока реализации или устойчивого темпа."
    return "Коммерческий статус по выполнению, сезонному наблюдению, устойчивому темпу и прогнозу."


def operational_summary(f, operations, p=None, second=None):
    sizes = diagnostic_evidence.size_state(f)
    confirmed = [label for key, label in OPERATION_ORDER[:4] if operations.get(key) is False]
    for key, label in (
        ("stop_needed", "нужна остановка подсортировки"),
        ("stores_reduction_needed", "нужно сокращение магазинов"),
        ("warehouse_transfer_needed", "нужен перенос через склад"),
        ("alternate_channel_needed", "нужна смена канала"),
    ):
        if f.get(key) is True:
            confirmed.append(label)
    if f.get("warehouse_skew_confirmed") is True:
        confirmed.append("складской перекос")
    if f.get("store_date") and p and p.get("entry") and f["store_date"] > p["entry"]:
        confirmed.append("поздняя поставка")
    if second and second.get("risk"):
        confirmed.append("риск второй поставки")
    signals = []
    if sizes["signal"] and not sizes["problem"]:
        signals.append("Проверить размерную доступность")
    if f.get("distribution") is not None and operations.get("distribution_ok") is None:
        signals.append("Проверить распределение")
    unknown = [
        label
        for key, label in OPERATION_ORDER
        if operations.get(key) is None or (key.endswith("checked") and operations.get(key) is False)
    ]
    signal = "Подтверждена проблема: " + ", ".join(confirmed) if confirmed else "; ".join(signals)
    if not signal and unknown:
        signal = "Проверить операционные условия: " + unknown[0]
    return {
        "operational_state": "ПОДТВЕРЖДЕННАЯ ПРОБЛЕМА"
        if confirmed
        else "ТРЕБУЕТ ПРОВЕРКИ"
        if signals or unknown
        else "НЕТ СИГНАЛА",
        "operational_signal": signal or None,
        "operational_details": {"confirmed": confirmed, "signals": signals, "unknown": unknown},
    }


def diagnose(f, m, p, operations, second, s):
    return diagnostic_evidence.diagnose(f, m, p, operations, second, s)


def pricing(f, m, p, s, operations, second, control):
    decision, change, reason = (
        "держать цену",
        "Без изменения",
        "Оснований для изменения цены не подтверждено.",
    )
    explicit_review = m.get("norms", {}).get("review_days", {}).get("value")
    review = (
        control + timedelta(days=explicit_review)
        if explicit_review is not None and explicit_review > 0 and float(explicit_review).is_integer()
        else None
    )
    review_window = f"{control + timedelta(days=7):%d.%m.%Y}–{control + timedelta(days=14):%d.%m.%Y}"
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
    elif operational_summary(f, operations, p, second)["operational_state"] != "НЕТ СИГНАЛА":
        decision, reason = (
            "наблюдать",
            "До цены: " + operational_summary(f, operations, p, second)["operational_signal"] + ".",
        )
    elif s == "ХИТ":
        if (
            all(operations[k] is True for k in ("representation_ok", "sizes_ok", "distribution_ok"))
            and not (second and second["risk"])
            and f.get("price_room") is True
            and m.get("season_pace_weeks", 0) >= 2
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
            cap = m.get("norms", {}).get("max_discount", {}).get("value")
            if cap is None or not 0 <= cap <= 1:
                decision, reason = (
                    "проверить данные",
                    "Не задан утверждённый предел скидки; значение из корпоративного диапазона не выбрано.",
                )
            elif f["discount"] >= cap:
                decision, reason = (
                    "держать цену",
                    "Достигнут предел скидки для текущего режима. Согласовать вывод или другой канал.",
                )
            else:
                decision = "снизить цену"
                if cap - f["discount"] < lo:
                    decision, reason = (
                        "держать цену",
                        "Утверждённый предел не позволяет минимальный шаг текущего режима; требуется согласование.",
                    )
                else:
                    change = f"Добавить {lo * 100:.0f}–{min(hi, cap - f['discount']) * 100:.0f} п.п.; итоговая скидка не выше {cap * 100:.0f}%"
                    reason = (
                        "Операционные причины проверены; прогноз подтверждает недобор при избыточном запасе."
                    )
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
        "review_date": review.isoformat() if review else None,
        "review_window": review_window,
        "review_limitation": None
        if review
        else "В правилах задано окно 7–14 дней; точная дата проверки ценового действия требует утверждённого срока.",
        "checks": checks,
    }


def recommend(f, m, p, s, causes, operations, price, second, control):
    owner = "Коммерческое планирование"
    review = None
    earliest = m.get("earliest_status_review_date")
    if earliest and date.fromisoformat(earliest) > control:
        review = date.fromisoformat(earliest)
    explicit_review = m.get("norms", {}).get("review_days", {}).get("value")
    if explicit_review:
        review = control + timedelta(days=explicit_review)
    if m.get("strategy", {}).get("kind") == "nos":
        action = "Проверить постоянное наличие, размерный ряд, покрытие и оборачиваемость; согласовать индивидуальные нормы. Сезонная распродажа по возрасту партии не назначается."
    elif s == "НЕДОСТАТОЧНО ДАННЫХ" and not any(
        operations[k] is False for k in ("representation_ok", "sizes_ok", "distribution_ok")
    ):
        action = "Уточнить отсутствующие данные и повторить оценку после достаточного срока наблюдения."
    elif s in ("РИСК", "АУТСАЙДЕР", "НЕДОСТАТОЧНО ДАННЫХ"):
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
            review = date.fromisoformat(price["review_date"]) if price["review_date"] else None
    elif s == "ХИТ":
        action = (
            price["change"] + ". Проверить возможность повтора и складской резерв для подтверждённого спроса."
        )
        if price["decision"] in ("повысить цену", "уменьшить скидку"):
            review = date.fromisoformat(price["review_date"]) if price["review_date"] else None
    else:
        action = "Сохранить цену и рабочую подсортировку; на следующем срезе сверить выполнение плана и прогноз к сроку."
    if "signature" in f.get("line", "").lower():
        action += " Для уникальной линии ранний выход на маркетплейсы исключён; приоритет Р1, Р2 и интернет-магазин."
    if "edition" in f.get("line", "").lower():
        action += " Пилотную линию расширять только после подтверждения спроса."
    if second and second["risk"]:
        action += " " + second["decision"].capitalize() + ": " + second["comment"]
        owner += " / Закупки / ВЭД / Логистика"
    if (
        p
        and "узкосезон" in p["type"].lower()
        and m["weeks_remaining"] is not None
        and m["weeks_remaining"] < 1
    ):
        review = None
    detail = action
    operational = operational_summary(f, operations, p, second)
    problem = operational["operational_signal"] or status_reason(m, p, s)
    if m.get("strategy", {}).get("kind") == "nos":
        action = "Проверить наличие, оборачиваемость и размерный ряд; согласовать индивидуальные нормы."
    elif operational["operational_state"] != "НЕТ СИГНАЛА":
        if diagnostic_evidence.size_state(f)["problem"]:
            problem = "Подтверждена проблема ходовых размеров"
            action = "Проверить ходовые размеры и согласовать восстановление размерного ряда."
            owner = "Категорийный менеджер / Розница"
        elif diagnostic_evidence.size_state(f)["signal"]:
            problem = "Размерная доступность требует проверки"
            action = "Проверить размеры по магазинам; подтвердить, затронуты ли ходовые размеры."
            owner = "Категорийный менеджер / Розница"
        else:
            action = "Сверить представленность, распределение и складской резерв до ценового решения."
    elif s == "НЕДОСТАТОЧНО ДАННЫХ":
        action = "Уточнить данные и повторить коммерческую оценку после достаточного сезонного наблюдения."
    else:
        action = price["change"] + ". Сверить выполнение плана и прогноз на следующем срезе."
    if second and second["risk"]:
        problem = "Подтверждённый риск второй поставки"
        action = "Согласовать объём и срок второй поставки с закупками и логистикой."
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
        "problem": problem,
        "action": action,
        "owner": owner,
        "review_date": review.isoformat() if review else None,
        "review_window": price["review_window"] if not review else None,
        "expected": "Подтвердить спрос, доступность и выполнение целевой реализации без необоснованной уценки.",
        "recommendation": action,
        "recommendation_detail": f"{happening} Причина: {causes['primary']}. {detail} "
        + (
            f"Проверка {review:%d.%m.%Y}."
            if review
            else "Точная дата проверки требует согласования; окно ценового действия: "
            + price["review_window"]
            + "."
        ),
    }
