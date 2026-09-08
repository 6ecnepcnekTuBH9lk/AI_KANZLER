from copy import deepcopy
from datetime import date

import pytest
from app.modules.merchandise import decisions, evidence, metrics, planning, presentation
from app.modules.merchandise.service import aggregate

START, END = date(2026, 9, 1), date(2027, 2, 28)


@pytest.mark.parametrize("raw,shown", [(1.4, 1), (1.5, 2), (2.5, 3), (-1.5, -2), (0, 0), (None, None)])
def test_half_up_physical_units(raw, shown):
    assert presentation.display_units(raw) == shown


@pytest.mark.parametrize(
    "execution,band",
    [
        (1.15, "ХИТ"),
        (1.149, "В ПЛАНЕ"),
        (0.85, "В ПЛАНЕ"),
        (0.849, "РИСК"),
        (0.7, "РИСК"),
        (0.699, "АУТСАЙДЕР"),
        (None, None),
    ],
)
def test_preliminary_has_no_operational_inputs(execution, band):
    assert decisions.preliminary_band(execution) == band


@pytest.mark.parametrize(
    "entry,days,start",
    [(date(2026, 8, 1), 6, "2026-09-01"), (date(2026, 9, 4), 3, "2026-09-04"), (None, None, None)],
)
def test_seasonal_observation_actual_entry_only(entry, days, start, merchandise_fact, article_plan):
    f = merchandise_fact
    f.update(store_date=entry, warehouse_date=date(2026, 7, 1))
    tr, _ = planning.build_plan(article_plan, None, f["base"], START, END)
    pct, units = planning.plan_at(tr, f["base"], date(2026, 9, 6), START, END)
    m, _ = metrics.calculate(f, article_plan, tr, date(2026, 9, 6), START, END, pct, units)
    assert m["season_observation_days"] == days
    assert m["season_observation_start"] == start
    c = decisions.commercial_context(m, article_plan, date(2026, 9, 6))
    assert c["earliest_status_review_date"] == (
        "2026-09-14" if days == 6 else "2026-09-17" if days == 3 else None
    )


@pytest.mark.parametrize("execution,expected", [(1.2, "ХИТ"), (1.0, "В ПЛАНЕ"), (0.5, "АУТСАЙДЕР")])
def test_operations_and_second_risk_never_lower_commercial_status(execution, expected, article_plan):
    m = {
        "season_observation_days": 34,
        "execution": execution,
        "deadline": END.isoformat(),
        "pace": 100,
        "forecast": 800 if execution >= 1 else 400,
        "season_plan": 700,
        "season_pace_weeks": 4,
        "cover": 5,
        "weeks_remaining": 20,
        "operational_risk": True,
    }
    ops = dict.fromkeys(dict(decisions.OPERATION_ORDER), True)
    assert decisions.status(m, ops, None, date(2026, 10, 4), START, article_plan) == expected
    ops = dict.fromkeys(ops, False)
    assert decisions.status(m, ops, {"risk": True}, date(2026, 10, 4), START, article_plan) == expected
    m["season_observation_days"] = 6
    assert decisions.status(m, ops, None, date(2026, 9, 6), START, article_plan) == "НЕДОСТАТОЧНО ДАННЫХ"


def test_only_explicit_narrow_rule_allows_early_status(article_plan):
    m = {
        "norms": {"observation_days": {"value": 5, "source": "Утверждённый план"}},
        "season_observation_days": 6,
        "execution": 1,
        "deadline": END.isoformat(),
        "pace": 10,
        "forecast": 700,
        "season_plan": 700,
    }
    assert decisions.observation_rule(m, article_plan)["minimum_days"] == 14
    p = {**article_plan, "type": "узкосезонный"}
    assert decisions.observation_rule(m, p)["minimum_days"] == 5
    assert decisions.status(m, {}, None, date(2026, 9, 6), START, p) == "В ПЛАНЕ"


def test_aggregate_signals_not_confirmed_and_block_price(merchandise_fact, article_plan):
    f = {
        **merchandise_fact,
        "size_availability": 0.98,
        "broken_ratio": 0.08,
        "distribution": 0.95,
        "price_room": True,
    }
    f.update(dict.fromkeys(dict(decisions.OPERATION_ORDER), True))
    f["sizes_ok"], f["distribution_ok"] = None, None
    m = {"forecast": 800, "season_plan": 700, "cover": 5, "weeks_remaining": 20, "season_pace_weeks": 4}
    operations = decisions.operational_evidence(f, m, article_plan)
    assert operations["sizes_ok"] is None and operations["distribution_ok"] is None
    assert evidence.size_state(f)["signal"] and not evidence.size_state(f)["problem"]
    assert decisions.operational_summary(f, operations)["operational_state"] == "ТРЕБУЕТ ПРОВЕРКИ"
    assert (
        decisions.pricing(f, m, article_plan, "ХИТ", operations, None, date(2026, 10, 4))["decision"]
        == "наблюдать"
    )
    f["sizes_ok"] = False
    operations = decisions.operational_evidence(f, m, article_plan)
    assert operations["sizes_ok"] is False and evidence.size_state(f)["problem"]
    assert decisions.operational_summary(f, operations)["operational_state"] == "ПОДТВЕРЖДЕННАЯ ПРОБЛЕМА"
    operations = dict.fromkeys(operations, True)
    operations["stop_checked"] = False
    assert decisions.operational_summary({}, operations)["operational_state"] == "ТРЕБУЕТ ПРОВЕРКИ"


def test_preseason_known_boundary_sum_daily_priority_and_no_batch_leak(merchandise_fact, article_plan):
    f = deepcopy(merchandise_fact)
    f["weekly"] = {date(2026, 8, 17): None, date(2026, 8, 24): 14, date(2026, 8, 31): 7}
    season, pre, qa = metrics.sales_window(f, START, date(2026, 9, 6), END)
    assert season == 6 and pre == 15
    assert any("пропорциональным" in x for x in qa) and any("по известным" in x for x in qa)
    f.update(sales_total=None, second_not_arrived=True)
    p = {**article_plan, "second_date": date(2026, 12, 1), "second_qty": 500}
    m = {"base": 1000, "pace": 10, "preseason": pre, "preseason_partial": True, "season_fact": season}
    assert decisions.second_wave(f, m, p, date(2026, 9, 6), END)["first_sales"] is None
    f["daily"] = {date(2026, 8, 31): 3, **{date(2026, 9, d): 2 for d in range(1, 7)}}
    season, pre, qa = metrics.sales_window(f, START, date(2026, 9, 6), END)
    assert season == 12 and pre == 3 and not qa


def test_known_sums_and_distinct_comparable_sets_keep_raw_values():
    rows = [
        {"base": 100, "plan_units": 1.4, "season_fact": 1.5, "forecast": 2.5, "status": "ХИТ"},
        {"base": None, "plan_units": 1.4, "season_fact": 1.5, "forecast": None, "status": "ХИТ"},
        {
            "base": 200,
            "plan_units": None,
            "season_fact": None,
            "forecast": None,
            "status": "НЕДОСТАТОЧНО ДАННЫХ",
        },
    ]
    snapshot = deepcopy(rows)
    a = aggregate(rows)
    assert a["known_base_units"] == 300 and a["base_known_articles"] == 2
    assert a["known_plan_units"] == 2.8 and a["plan_known_articles"] == 2
    assert a["known_fact_units"] == 3 and a["fact_known_articles"] == 2
    assert a["st"] == 0.015 and a["st_comparable_articles"] == 1
    assert a["execution"] == pytest.approx(3 / 2.8) and a["comparable_articles"] == 2
    assert presentation.display_units(a["plan_units"]) == 3  # NOT sum(round(1.4)) == 2.
    assert a["execution"] == pytest.approx(3 / 2.8) and rows == snapshot
    assert aggregate([{"status": "НЕДОСТАТОЧНО ДАННЫХ", "plan_units": None}])["known_fact_units"] is None


def test_quality_dedup_and_grouping_retain_unknown():
    row = {
        "severity": "Предупреждение",
        "source": "Факт",
        "article": "A",
        "message": "Нет базы",
        "source_row": 5,
    }
    rows = [row, row.copy(), {**row, "article": "B", "source_row": 6}]
    assert len(presentation.deduplicate_quality(rows)) == 2
    assert presentation.group_quality(rows)[0]["affected_articles"] == 2


def test_review_date_without_approved_exact_rule_is_unknown(merchandise_fact, article_plan):
    m = {"execution": None, "season_observation_days": None, "age": None, "norms": {}}
    ops = dict.fromkeys(dict(decisions.OPERATION_ORDER), None)
    price = decisions.pricing(merchandise_fact, m, article_plan, "НЕДОСТАТОЧНО ДАННЫХ", ops, None, START)
    action = decisions.recommend(
        merchandise_fact,
        m,
        article_plan,
        "НЕДОСТАТОЧНО ДАННЫХ",
        {"primary": "нет данных"},
        ops,
        price,
        None,
        START,
    )
    assert action["review_date"] is None and action["review_window"]
    assert len(action["action"]) < 150 and len(action["recommendation"]) < 150
