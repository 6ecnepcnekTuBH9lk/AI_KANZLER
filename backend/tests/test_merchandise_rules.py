from copy import deepcopy
from datetime import date, timedelta

import pytest
from app.modules.merchandise import decisions, evidence, importers, metrics, norms, planning
from app.shared.excel import Cell, Table

START, END, CONTROL = date(2026, 9, 1), date(2027, 2, 28), date(2026, 10, 4)


@pytest.mark.parametrize("term", ["", "3–6 месяцев", "4-6 месяцев", "до 6 месяцев", "около 180 дней"])
def test_no_point_chosen_from_term_range(term, article_plan):
    article_plan["term"] = term
    assert metrics.deadline_for(article_plan, START, END) is None


def test_exact_term_and_missing_deadline(merchandise_fact, article_plan):
    article_plan["term"] = "4 месяца"
    assert metrics.deadline_for(article_plan, START, END) == date(2026, 12, 1)
    article_plan["term"] = ""
    tr, _ = planning.build_plan(article_plan, None, 1000, START, END)
    pct, units = planning.plan_at(tr, 1000, CONTROL, START, END)
    m, qa = metrics.calculate(merchandise_fact, article_plan, tr, CONTROL, START, END, pct, units)
    assert all(m[k] is None for k in ("deadline", "required", "forecast", "weeks_remaining"))
    assert any("диапазона" in q for q in qa)


def test_normalization_and_partial_curve_are_distinct(article_plan):
    cat = deepcopy(article_plan)
    article_plan.update(month_mode="pct", months={m: 1 / 6 for m in (9, 10, 11, 12, 1, 2)})
    tr, _ = planning.build_plan(article_plan, cat, 1000, START, END)
    assert sum(tr["daily"].values()) == pytest.approx(0.7)
    # A week straddling September/October contains both monthly allocations.
    assert sum(tr["daily"][date(2026, 9, 28) + timedelta(days=i)] for i in range(7)) == pytest.approx(
        0.7 / 6 * (3 / 30 + 4 / 31)
    )
    article_plan["months"][9] = None
    assert planning.build_plan(article_plan, cat, 1000, START, END)[0] is None
    article_plan["months"] = dict.fromkeys(article_plan["months"])
    assert planning.build_plan(article_plan, cat, 1000, START, END)[0] is not None


def test_preseason_and_late_delivery_do_not_shift_official_execution(merchandise_fact, article_plan):
    merchandise_fact["weekly"][date(2026, 8, 31)] = 70
    merchandise_fact["weekly"][date(2026, 8, 24)] = 10
    tr, _ = planning.build_plan(article_plan, None, 1000, START, END)
    pct, units = planning.plan_at(tr, 1000, CONTROL, START, END)
    first, _ = metrics.calculate(merchandise_fact, article_plan, tr, CONTROL, START, END, pct, units)
    merchandise_fact["weekly"][date(2026, 8, 24)] = 100000
    merchandise_fact["store_date"] = CONTROL
    second, _ = metrics.calculate(merchandise_fact, article_plan, tr, CONTROL, START, END, pct, units)
    assert first["preseason"] != second["preseason"]
    for key in ("plan_pct", "plan_units", "season_fact", "st", "execution"):
        assert first[key] == second[key]


def test_nos_does_not_inherit_seasonal_status(merchandise_fact, article_plan):
    m = {
        "age": 35,
        "execution": 1.0,
        "deadline": END.isoformat(),
        "pace": 10,
        "forecast": 700,
        "season_plan": 700,
        "cover": 10,
        "weeks_remaining": 20,
    }
    ops = dict.fromkeys(dict(decisions.OPERATION_ORDER), True)
    m["strategy"] = norms.strategy(merchandise_fact, article_plan)
    assert decisions.status(m, ops, None, CONTROL, START, article_plan) == "В ПЛАНЕ"
    article_plan["type"] = "NOS"
    m["strategy"] = norms.strategy(merchandise_fact, article_plan)
    assert decisions.status(m, ops, None, CONTROL, START, article_plan) == "НЕДОСТАТОЧНО ДАННЫХ"
    d = decisions.diagnose(merchandise_fact, m, article_plan, ops, None, "НЕДОСТАТОЧНО ДАННЫХ")
    price = decisions.pricing(merchandise_fact, m, article_plan, "НЕДОСТАТОЧНО ДАННЫХ", ops, None, CONTROL)
    action = decisions.recommend(
        merchandise_fact, m, article_plan, "НЕДОСТАТОЧНО ДАННЫХ", d, ops, price, None, CONTROL
    )
    assert "оборачиваемость" in action["action"]
    assert "избыточная глубина" not in [e["diagnosis"] for e in d["evidence"]]


@pytest.mark.parametrize(
    "field,value", [("size_availability", 0.8), ("broken_ratio", 0.01), ("broken_stores", 1)]
)
def test_aggregate_sizes_proven_not_guessed(field, value, merchandise_fact, article_plan):
    before = metrics.sales_window(merchandise_fact, START, CONTROL, END)
    merchandise_fact[field] = value
    ops = decisions.operational_evidence(merchandise_fact, {}, article_plan)
    d = evidence.diagnose(merchandise_fact, {}, article_plan, ops, None, "НЕДОСТАТОЧНО ДАННЫХ")
    assert d["primary"] == "проблема размерной доступности"
    assert field in [x["field"] for x in d["evidence"][0]["inputs"]]
    assert not d["sizes"]["core_sizes_confirmed"] and d["missing_evidence"]
    assert before == metrics.sales_window(merchandise_fact, START, CONTROL, END)


def test_no_size_evidence_is_not_confirmed_healthy():
    assert evidence.size_state({})["state"] == "Нет данных для проверки"
    s = evidence.size_state({"sizes": 6, "avg_sizes": 6, "broken_ratio": 0})
    assert s["state"] == "Признаков проблемы нет" and not s["core_sizes_confirmed"]


def test_planned_delivery_is_not_actual_party_evidence(merchandise_fact, article_plan):
    article_plan.update(second_date=date(2026, 12, 1), second_qty=200)
    m = {"base": 1000, "pace": 10, "pace_weeks": 4}
    wave = decisions.second_wave(merchandise_fact, m, article_plan, CONTROL, END)
    assert wave["first_sales"] is None and wave["forecast"] is None
    assert wave["scenario_forecast"] is not None and wave["scenario_risk"]
    assert not wave["risk"] and wave["missing_conditions"]
    merchandise_fact["second_not_arrived"] = True
    wave = decisions.second_wave(merchandise_fact, m, article_plan, CONTROL, END)
    assert wave["first_sales"] == 300 and wave["risk"]
    merchandise_fact["second_actual"] = date(2026, 10, 1)
    wave = decisions.second_wave(merchandise_fact, m, article_plan, CONTROL, END)
    assert wave["first_sales"] is None


def test_explicit_window_uses_end_not_first_date():
    headers = ["Артикул", "Коммерческое окно", "Окончание окна"]
    row = [Cell("6A-X"), Cell("01.09.2026–31.12.2026"), Cell(None)]
    t = Table("План", 1, headers, headers, [], [])
    assert importers.window_end(t, row) == date(2026, 12, 31)
    row[2] = Cell(date(2026, 11, 30))
    assert importers.window_end(t, row) == date(2026, 11, 30)


def test_distribution_and_warehouse_evidence(merchandise_fact, article_plan):
    f = merchandise_fact
    f["weekly"][date(2026, 8, 31)] = 70
    st_before = metrics.sales_window(f, START, CONTROL, END)[0] / f["base"]
    f.update(stores=0, warehouse=None, warehouse_known=50, distribution=0.2)
    ops = decisions.operational_evidence(f, {}, article_plan)
    d = evidence.diagnose(f, {}, article_plan, ops, None, "НЕДОСТАТОЧНО ДАННЫХ")
    assert d["primary"] == "недостаточная представленность"
    assert "складской перекос" in [e["diagnosis"] for e in d["evidence"]]
    assert "ошибочное распределение" not in [e["diagnosis"] for e in d["evidence"]]
    f["distribution_ok"] = False
    ops = decisions.operational_evidence(f, {}, article_plan)
    assert "ошибочное распределение" in [
        e["diagnosis"] for e in evidence.diagnose(f, {}, article_plan, ops, None, "РИСК")["evidence"]
    ]

    assert st_before == 0.28
    assert metrics.sales_window(f, START, CONTROL, END)[0] / f["base"] == st_before


@pytest.mark.parametrize(
    "need,check",
    [
        ("replenishment_needed", "replenishment_ok"),
        ("stop_needed", "stop_checked"),
        ("stores_reduction_needed", "stores_checked"),
        ("warehouse_transfer_needed", "warehouse_checked"),
        ("alternate_channel_needed", "channel_checked"),
    ],
)
def test_confirmed_operational_need_blocks_price(need, check, merchandise_fact, article_plan):
    merchandise_fact.update(dict.fromkeys(dict(decisions.OPERATION_ORDER), True))
    merchandise_fact[need] = True
    ops = decisions.operational_evidence(merchandise_fact, {}, article_plan)
    assert ops[check] is False
    price = decisions.pricing(merchandise_fact, {}, article_plan, "РИСК", ops, None, CONTROL)
    assert price["decision"] == "наблюдать"


def test_unperformed_check_is_not_a_negative_business_fact(article_plan):
    ops = dict.fromkeys(dict(decisions.OPERATION_ORDER), True)
    ops["stop_checked"] = False
    m = {
        "age": 35,
        "execution": 1,
        "deadline": END.isoformat(),
        "pace": 10,
        "forecast": 700,
        "season_plan": 700,
    }
    assert decisions.status(m, ops, None, CONTROL, START, article_plan) == "В ПЛАНЕ"


def test_second_wave_missing_inputs_never_approve_full_receipt(merchandise_fact, article_plan):
    f = merchandise_fact
    f.update(sales_total=900, economics_ok=True, capacity_ok=True, channel_ok=True, second_not_arrived=True)
    article_plan.update(second_date=date(2026, 12, 1), second_qty=200)
    m = {"base": 1000, "pace": 100, "pace_weeks": 4, "cover": 10}
    wave = decisions.second_wave(f, m, article_plan, CONTROL, END)
    assert wave["completed_weeks"] == 4 and wave["target70"] == 700
    assert (
        wave["decision"] == "согласовать условия поставки" and "запас в месяцах" in wave["missing_conditions"]
    )
    m["base"] = None
    f["inventory_months_ok"] = True
    wave = decisions.second_wave(f, m, article_plan, CONTROL, END)
    assert wave["decision"] == "согласовать условия поставки" and wave["target70"] is None


def test_norms_priority_semantic_not_coordinate():
    headers = [
        "Вид номенклатуры",
        "Вид ассортимента",
        "Наценка",
        "Утверждённый предел скидки",
        "Целевая маржа",
    ]
    row = [Cell("Брюки"), Cell("Брюки"), Cell(3.5), Cell(0.3, "0%"), Cell(0.6, "0%")]
    t = Table("Нормативы", 1, headers, headers, [], [(2, row)])
    cat = {"norms": norms.read(t, row, 2)}
    article = {"norms": {"markup": {"value": 4, "raw": "4"}}}
    resolved = norms.resolve(article, cat, 9)
    assert resolved["markup"]["value"] == 4 and resolved["max_discount"]["value"] == 0.3
    reordered = Table("Нормативы", 1, headers[::-1], headers[::-1], [], [(2, row[::-1])])
    assert {k: v["value"] for k, v in norms.read(reordered, row[::-1], 2).items()} == {
        k: v["value"] for k, v in cat["norms"].items()
    }
    article["norms"]["markup"] = {"value": None, "raw": "3–4"}
    assert norms.resolve(article, cat, 9)["markup"]["invalid"]


def test_ratio_units_use_header_not_sheet_name():
    h = ["Артикул", "Код", "Коэффициент размерной доступности", "Доля магазинов с выбитостью (%)"]
    row = [Cell("6A-X"), Cell("001"), Cell(1), Cell(1)]
    t = Table("TDSheet", 1, h, h, [], [(2, row)])
    f = importers.read_fact(t, "ОЗ26", set())[0]
    assert f["size_availability"] == 1 and f["broken_ratio"] == 0.01


def test_invalid_explicit_curve_and_target_do_not_fallback(article_plan):
    cat = deepcopy(article_plan)
    article_plan.update(invalid_months=True)
    assert planning.build_plan(article_plan, cat, 1000, START, END)[0] is None
    article_plan.update(invalid_months=False, target=None, target_raw="70–80%")
    assert planning.build_plan(article_plan, cat, 1000, START, END)[0] is None


def test_gmroi_requires_matching_period_and_valid_cost_stock(merchandise_fact, article_plan):
    f = merchandise_fact
    f.update(gross_profit=140, avg_cost_stock=100)
    m, _ = metrics.calculate(f, article_plan, None, CONTROL, START, END, None, None)
    assert m["gmroi"] is None
    f["gmroi_scope_ok"] = True
    m, _ = metrics.calculate(f, article_plan, None, CONTROL, START, END, None, None)
    assert m["gmroi"] == 1.4
    f["avg_cost_stock"] = 0
    m, _ = metrics.calculate(f, article_plan, None, CONTROL, START, END, None, None)
    assert m["gmroi"] is None


def test_hit_price_requires_seasonal_evidence(merchandise_fact, article_plan):
    merchandise_fact["price_room"] = True
    ops = dict.fromkeys(dict(decisions.OPERATION_ORDER), True)
    m = {"forecast": 900, "season_plan": 700, "cover": 10, "weeks_remaining": 20, "season_pace_weeks": 0}
    assert (
        decisions.pricing(merchandise_fact, m, article_plan, "ХИТ", ops, None, CONTROL)["decision"]
        == "держать цену"
    )
    m["season_pace_weeks"] = 4
    price = decisions.pricing(merchandise_fact, m, article_plan, "ХИТ", ops, None, CONTROL)
    assert price["decision"] == "уменьшить скидку" and price["review_date"] is None
    m["norms"] = {"review_days": {"value": 10}}
    assert (
        decisions.pricing(merchandise_fact, m, article_plan, "ХИТ", ops, None, CONTROL)["review_date"]
        == "2026-10-14"
    )
