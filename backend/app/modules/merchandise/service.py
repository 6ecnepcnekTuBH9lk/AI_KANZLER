from collections import defaultdict

from app.core.exceptions import InputError
from app.modules.merchandise import decisions, history, importers, metrics, planning, reporting
from app.shared.excel import norm


def run(files, options, output_dir, progress, sessions=None):
    progress(5, "Определение структуры и ролей файлов")
    roles = importers.detect_roles(files)
    season, control, start, end, metadata_qa = importers.metadata(roles, options)
    plans = importers.read_plans(roles["article"][1])
    category_plans = importers.read_plans(roles["category"][1], category=True)
    facts = importers.read_fact(roles["fact"][1], season, {p["article"] for p in plans})
    if not facts:
        raise InputError("В фактических продажах не найдены артикулы текущей коллекции.")
    plan_duplicates = importers.duplicate_keys(plans, lambda p: p["article"])
    code_duplicates = importers.duplicate_keys(plans, lambda p: p["code"])
    fact_duplicates = importers.duplicate_keys(facts, lambda f: f["article"])
    by_article = {p["article"]: p for p in plans}
    by_code = {p["code"]: p for p in plans if p["code"]}
    categories = defaultdict(list)
    for p in category_plans:
        categories[(norm(p["kind"]), norm(p["assortment"]))].append(p)
    sections = {key: [] for key in reporting.SHEETS if key != "summary"}
    qa = sections["data-quality"]
    for message, severity in metadata_qa:
        qa.append(
            {
                "severity": severity,
                "article": None,
                "source": "Параметры запуска",
                "source_row": None,
                "message": message,
            }
        )
    weekly_rows = []
    total = len(facts)
    processed = set()
    for i, f in enumerate(facts):
        article = f["article"]
        if article in processed:
            continue
        processed.add(article)
        notes = []
        critical = False
        p = by_article.get(article)
        cp = by_code.get(f["code"])
        if p and cp and p["article"] != cp["article"]:
            notes.append("Артикул и код дают противоречивое соответствие поартикульному плану.")
            critical = True
            p = None
        elif not p and cp and f["code"] not in code_duplicates:
            p = cp
            notes.append("Поартикульный план сопоставлен по коду; обозначение артикула отличается.")
        if article in plan_duplicates or article in fact_duplicates or f["code"] in code_duplicates:
            notes.append(
                "Повторяющийся артикул или конфликтующий код: строки не объединены автоматически, расчёт заблокирован."
            )
            critical = True
        if article in fact_duplicates:
            # Neither duplicate is a trustworthy article-level denominator.
            f["base"] = None
        for key in ("base", "stock", "sizes", "avg_sizes", "stores", "effective_stores", "price"):
            if f.get(key) is not None and f[key] < 0:
                notes.append(
                    "Обнаружено отрицательное значение показателя «"
                    + importers.ALIASES[key][0]
                    + "». Требуется сверка источника."
                )
                f[key] = None
                critical = True
        cat_matches = categories.get((norm(f["kind"]), norm(f["assortment"])), [])
        cat = cat_matches[0] if len(cat_matches) == 1 else None
        if cat is None:
            notes.append(
                "Не найден однозначный точный категорийный норматив по виду номенклатуры и виду ассортимента."
            )
        trajectory, plan_notes = planning.build_plan(p, cat, f["base"], start, end)
        notes += plan_notes
        pct, units = planning.plan_at(trajectory, f["base"], control, start, end)
        m, metric_notes = metrics.calculate(f, p, trajectory, control, start, end, pct, units)
        notes += metric_notes
        if critical:
            for key in (
                "season_fact",
                "st",
                "execution",
                "gap_pp",
                "gap_units",
                "forecast",
                "forecast_st",
                "plan_units",
                "plan_pct",
                "season_plan",
            ):
                m[key] = None
            trajectory = None
        for key, label in [
            ("stock", "текущий остаток"),
            ("store_date", "дата поступления в магазины"),
            ("price", "текущая цена"),
            ("discount", "скидка"),
            ("markup", "наценка"),
            ("margin", "маржа"),
            ("sizes", "размеры"),
            ("stores", "представленность"),
            ("distribution", "распределение"),
        ]:
            if f.get(key) is None:
                notes.append(f"Отсутствует показатель: {label}.")
        operations = decisions.operational_evidence(f, m, p)
        unknown = [label for key, label in decisions.OPERATION_ORDER if operations[key] is None]
        if unknown:
            notes.append(
                "Нет подтверждения операционных условий: "
                + ", ".join(unknown)
                + ". Ценовое действие ограничено."
            )
        second = decisions.second_wave(f, m, p, control, end)
        if second:
            sections["second-wave"].append(second)
            if second["first_sales"] is None:
                notes.append(second["comment"])
        s = decisions.status(m, operations, second, control, start, p, critical)
        causes = decisions.diagnose(f, m, p, operations, second, s)
        price = decisions.pricing(f, m, p, s, operations, second, control)
        action = decisions.recommend(f, m, p, s, causes, operations, price, second, control)
        historical = history.context(f, control)
        if not historical["weekly_shares"]:
            notes.append(historical["text"])
        for note in dict.fromkeys(notes):
            qa.append(
                {
                    "severity": "Ошибка" if critical else "Предупреждение",
                    "article": article,
                    "source": "Актуальные входные файлы",
                    "source_row": f["source_row"],
                    "message": note,
                }
            )
        details = {
            k: f.get(k)
            for k in (
                "sizes",
                "avg_sizes",
                "size_availability",
                "stores",
                "effective_stores",
                "broken_ratio",
                "distribution",
                "price",
                "discount",
                "markup",
                "margin",
            )
        }
        a = {
            **m,
            **details,
            "article": article,
            "code": f["code"],
            "category": p["category"] if p and p["category"] else f["kind"] or f["category"],
            "kind": f["kind"],
            "assortment": f["assortment"],
            "type": p["type"] if p else None,
            "status": s,
            "primary_cause": causes[0],
            "secondary_cause": causes[1],
            "recommendation": action["recommendation"],
            "owner": action["owner"],
            "review_date": action["review_date"],
            "warehouse_share": metrics.ratio(f["warehouse"], f["stock"]),
            "historical_text": historical["text"],
            "historical": historical,
            "qa_text": " ".join(dict.fromkeys(notes)),
            "second_date": second["second_date"] if second else None,
            "second_qty": second["second_qty"] if second else None,
            "weekly_actual": [
                {"week_start": d.isoformat(), "quantity": v} for d, v in sorted(f["weekly"].items())
            ],
            "weekly_plan": trajectory["weekly"] if trajectory else [],
            "operations": price["checks"],
            "channel_distribution": f["channel_distribution"],
            "pricing": price,
            "second_wave": second,
        }
        sections["articles"].append(a)
        sections["pricing"].append(price)
        sections["actions"].append(action)
        week_row = {k: a[k] for k in ("article", "code", "base", "target")}
        for point in a["weekly_plan"]:
            week_row[point["week_start"]] = point["pct"]
            weekly_rows.append(
                {
                    "article": article,
                    "week_start": point["week_start"],
                    "kind": "plan_pct",
                    "quantity": point["pct"],
                }
            )
        sections["weekly-plan"].append(week_row)
        weekly_rows.extend(
            {"article": article, "week_start": d.isoformat(), "kind": "fact", "quantity": v}
            for d, v in f["weekly"].items()
        )
        if i % 10 == 0:
            progress(15 + int((i + 1) / total * 70), f"Рассчитано артикулов: {i + 1} из {total}")
    for p in plans:
        if p["article"] not in processed:
            qa.append(
                {
                    "severity": "Предупреждение",
                    "article": p["article"],
                    "source": "Поартикульный план",
                    "source_row": p["source_row"],
                    "message": "Артикул плана не найден в фактических продажах текущей коллекции.",
                }
            )
    grouped = defaultdict(list)
    for a in sections["articles"]:
        grouped[(a["category"], a["assortment"])].append(a)
    for (category, assortment), rows in grouped.items():
        c = aggregate(rows)
        c.update(
            category=category,
            assortment=assortment,
            conclusion="План и факт агрегированы из рассчитанных артикулов. Неполные показатели не подменяются нулём.",
        )
        sections["categories"].append(c)
    summary = aggregate(sections["articles"])
    counts = {s: sum(a["status"] == s for a in sections["articles"]) for s in decisions.STATUSES}
    display = {
        "Сезон": season,
        "Контрольная дата анализа": control.strftime("%d.%m.%Y"),
        "Официальный период выполнения плана": f"{start:%d.%m.%Y}–{end:%d.%m.%Y}",
        "Количество анализируемых артикулов": summary["count"],
        "Суммарный начальный остаток": summary["base"],
        "План на дату, ед.": summary["plan_units"],
        "План на дату, %": summary["plan_pct"] * 100 if summary["plan_pct"] is not None else None,
        "Факт продаж сезона, ед.": summary["season_fact"],
        "Факт реализации сезона, %": summary["st"] * 100 if summary["st"] is not None else None,
        "Выполнение плана на дату, %": summary["execution"] * 100
        if summary["execution"] is not None
        else None,
        "Прогноз продаж, ед.": summary["forecast"],
        **counts,
        "Риски второй поставки": sum(s["risk"] for s in sections["second-wave"]),
        "Кандидаты на повышение цены": sum(
            p["decision"] in ("повысить цену", "уменьшить скидку") for p in sections["pricing"]
        ),
        "Кандидаты на снижение цены": sum(p["decision"] == "снизить цену" for p in sections["pricing"]),
        "Артикулы с проблемой размеров": sum(
            a["primary_cause"] == "выбитые размеры" for a in sections["articles"]
        ),
        "Артикулы с проблемой распределения": sum(
            a["primary_cause"] == "ошибочное распределение" for a in sections["articles"]
        ),
        "Сообщения качества данных": len(qa),
    }
    for key, label in (
        ("base", "Начальный остаток"),
        ("plan_units", "План на дату"),
        ("season_fact", "Факт сезона"),
        ("forecast", "Прогноз"),
    ):
        coverage = summary["coverage"][key]
        display[f"{label}: сумма по доступным данным, ед."] = coverage["known_sum"]
        display[f"{label}: артикулов с данными"] = coverage["known_count"]
    display["Сопоставимый набор: артикулов с базой, планом и фактом"] = summary["comparable"]["count"]
    comparable_execution = summary["comparable"]["execution"]
    display["Сопоставимый набор: выполнение плана, %"] = (
        comparable_execution * 100 if comparable_execution is not None else None
    )
    week_columns = []
    for d in planning.weekly_ends(start, end):
        monday = d - planning.timedelta(days=d.weekday())
        iso = d.isocalendar()
        week_columns.append(
            {"week_start": monday.isoformat(), "label": f"План неделя {iso.week} {iso.year}, % накоп."}
        )
    result = {
        "title": f"{season} · {control:%d.%m.%Y}",
        "season": season,
        "control_date": control.isoformat(),
        "season_start": start.isoformat(),
        "season_end": end.isoformat(),
        "summary": summary,
        "counts": counts,
        "display_summary": display,
        "week_columns": week_columns,
        "schemas": reporting.SCHEMAS,
        "sources": {role: f.original_name for role, (f, t) in roles.items()},
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    output_name = f"KANZLER_Контроль_ассортимента_{control.isoformat()}.xlsx"
    path = output_dir / output_name
    progress(92, "Формирование и проверка Excel")
    reporting.export(result, sections, path)
    return result, sections, path, output_name, weekly_rows


def aggregate(rows):
    def total(key):
        values = [r.get(key) for r in rows]
        return sum(values) if values and all(v is not None for v in values) else None

    result = {
        k: total(k)
        for k in (
            "base",
            "plan_units",
            "season_fact",
            "previous_week",
            "current_week",
            "avg2",
            "forecast",
            "season_plan",
            "stock",
        )
    }
    result.update(
        count=len(rows),
        plan_pct=metrics.ratio(result["plan_units"], result["base"]),
        st=metrics.ratio(result["season_fact"], result["base"]),
        execution=metrics.ratio(result["season_fact"], result["plan_units"]),
    )
    result.update(
        {
            key: sum(r["status"] == s for r in rows)
            for key, s in [
                ("hits", "ХИТ"),
                ("on_plan", "В ПЛАНЕ"),
                ("risks", "РИСК"),
                ("outsiders", "АУТСАЙДЕР"),
            ]
        }
    )
    result["planned_count"] = sum(r["plan_units"] is not None for r in rows)
    # Known-value subtotals are explicitly separate from complete collection totals.
    result["coverage"] = {
        k: {
            "known_count": sum(r.get(k) is not None for r in rows),
            "known_sum": sum(r[k] for r in rows if r.get(k) is not None),
        }
        for k in ("base", "plan_units", "season_fact", "forecast")
    }
    comparable = [r for r in rows if all(r.get(k) is not None for k in ("base", "plan_units", "season_fact"))]
    result["comparable"] = {
        "count": len(comparable),
        "plan_units": sum(r["plan_units"] for r in comparable),
        "season_fact": sum(r["season_fact"] for r in comparable),
    }
    result["comparable"]["execution"] = metrics.ratio(
        result["comparable"]["season_fact"], result["comparable"]["plan_units"]
    )
    return result
