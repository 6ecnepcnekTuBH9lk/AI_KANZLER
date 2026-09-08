"""Rule and metamorphic regression against Alta evidence captured on 2026-09-08."""

import base64
import hashlib
import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from app.core.exceptions import SourceUnavailable
from app.modules.tnved import apparel, footwear
from app.modules.tnved.alta import AltaClient, CandidateFinder
from app.modules.tnved.classifier import CandidateValidator, ClassificationEngine
from app.modules.tnved.conditions import PathContext
from app.modules.tnved.features import extract_features

FIXTURE = Path(__file__).parent / "fixtures/tnved"
ALTA = json.loads((FIXTURE / "alta.json").read_text(encoding="utf-8"))
BASELINE = json.loads((FIXTURE / "baseline.json").read_text(encoding="utf-8"))
EXPECTED = json.loads((FIXTURE / "expected.json").read_text(encoding="utf-8"))


def engine():
    client = SimpleNamespace(verify=lambda code: deepcopy(ALTA["cards"][code]))
    result = ClassificationEngine(client)
    routing = CandidateFinder(client)
    result.finder.find = lambda f: sorted({c for h in routing.headings(f) for c in ALTA["headings"][h]})
    return result


def garment(kind="Рубашка", composition="100% хлопок", **fields):
    return {"Номенклатура": kind, "Пол": "Мужской", "Трикотаж": "Да", "Состав": composition, **fields}


def shoe(**fields):
    return {
        "Номенклатура": "Лоферы",
        "Пол": "Мужской",
        "Материал верха": "натуральная кожа",
        "Материал подошвы": "резина",
        "Закрывает лодыжку": "Нет",
        "Длина стельки": "27 см",
        "Спортивная обувь": "Нет",
        "Металлический подносок": "Нет",
        "Домашняя обувь": "Нет",
        "Деревянная платформа без внутренней стельки": "Нет",
        "Союзка из ремешков": "Нет",
        "Союзка с вырезами": "Нет",
        "Ремешки через подъем и большой палец": "Нет",
        **fields,
    }


@pytest.mark.parametrize(
    "composition, material",
    [
        ("100% хлопок", "хлопок"),
        ("хлопок 70%, полиэстер 30%", "хлопок"),
        ("70% хлопок, 30% полиэстер", "хлопок"),
        ("50% хлопок, 50% полиэстер", "синтетические"),
        ("43% лен, 32% полиэстер, 25% шерсть", "лен"),
        ("50% шерсть, 30% нейлон, 20% вискоза", "химические"),
        ("40% хлопок, 35% полиэстер, 25% вискоза", "химические"),
        ("70% хлопок, 30% неизвестное волокно", None),
        ("80% хлопок", None),
        ("100% микрофибра", None),
        ("100% тенсел", "искусственные"),
        ("100% полипропилен", "синтетические"),
        ("100% спандекс", "синтетические"),
    ],
)
def test_mixture_rules(composition, material):
    f = extract_features(garment(composition=composition))
    assert f.material == material
    assert f.material_rule["source"] == "https://www.alta.ru/poyasnenia/R11/"


def test_composition_parts_unknown_and_ties_are_retained():
    a = extract_features(
        garment(
            composition="Подкладка: 100% полиэстер; Основная ткань: хлопок 70%, лен 30%; Наполнитель: 100% пух"
        )
    )
    assert a.material == "хлопок" and a.composition_total == 100
    assert "подкладка" in a.parts and len(a.components) == 2
    b = extract_features(garment(composition="50% хлопок, 50% полиэстер"))
    assert set(b.tied_materials) == {"хлопок", "синтетические"}
    c = extract_features(garment(composition="90% хлопок, 10% секретное волокно"))
    assert c.unknown_fibers == ["секретное волокно"] and c.composition_total == 100


@pytest.mark.parametrize(
    "field,old,new",
    [
        ("Бренд", "ALPHA", "BETA"),
        ("Бренд", "ALPHA", "Пиджак"),
        ("Цвет", "красный", "синий"),
        ("Артикул", "SKU-1", "SKU-2"),
    ],
)
def test_identity_metamorphic_even_inside_title(field, old, new):
    a = garment(**{field: old, "Наименование": "Рубашка " + old})
    b = garment(**{field: new, "Наименование": "Рубашка " + new})
    first, second = extract_features(a), extract_features(b)
    assert first.signature == second.signature
    assert engine().classify(first)["code"] == engine().classify(second)["code"] == "6105100000"


@pytest.mark.parametrize(
    "field,value",
    [("Пол", "Женский"), ("Трикотаж", "Нет"), ("Состав", "100% шелк"), ("Конструкция", "специальная")],
)
def test_significant_change_changes_signature(field, value):
    assert extract_features(garment()).signature != extract_features(garment(**{field: value})).signature


def test_unknown_fibers_and_chemical_fiber_types_do_not_merge():
    assert (
        extract_features(garment(composition="100% A-волокно")).signature
        != extract_features(garment(composition="100% B-волокно")).signature
    )
    assert (
        extract_features(garment(composition="100% полиэстер")).signature
        != extract_features(garment(composition="100% полиамид")).signature
    )


def test_knit_gender_and_material_change_routing():
    e = engine()
    assert e.classify(extract_features(garment()))["code"] == "6105100000"
    assert e.classify(extract_features(garment(Трикотаж="Нет")))["code"] == "6205200000"
    assert e.classify(extract_features(garment(composition="100% полиэстер")))["code"] == "6105201000"
    finder = CandidateFinder(None)
    assert finder.headings(extract_features(garment(Пол="Женский"))) == ["6106"]
    assert set(finder.headings(extract_features(garment(Пол=None)))) == {"6105", "6106"}


def test_missing_required_feature_and_conflict_never_confirm():
    assert engine().classify(extract_features(garment(Состав=None)))["code"] is None
    assert engine().classify(extract_features(garment(Трикотаж="Нет", Наименование="Трикотажная рубашка")))[
        "reason_categories"
    ] == ["CONFLICTING_INPUT"]


def test_blazer_cannot_match_trousers_parent_or_residual():
    f = extract_features(garment("Пиджак", "100% вискоза"))
    cards = [ALTA["cards"][c] for c in ALTA["headings"]["6103"]]
    context = PathContext(cards, apparel.predicate)
    assert CandidateValidator().assess(f, ALTA["cards"]["6103490002"], context).verdict == "excluded"
    assert engine().classify(f)["code"] == "6103390000"
    # Alta's virtual residual prefix sorts before its preceding 0001 leaf;
    # its position must be determined from actual descendant leaves.
    assert engine().classify(extract_features(garment("Брюки", "100% вискоза")))["code"] == "6103490001"


def test_residual_requires_excluding_professional_branch():
    row = garment("Пиджак", "100% полиэстер", Трикотаж="Нет")
    assert engine().classify(extract_features(row))["code"] is None
    assert (
        engine().classify(extract_features({**row, "Промышленная или профессиональная одежда": "Нет"}))[
            "code"
        ]
        == "6203339000"
    )
    assert (
        engine().classify(extract_features({**row, "Промышленная или профессиональная одежда": "Да"}))["code"]
        == "6203331000"
    )


def test_denim_requires_explicit_fabric_and_professional_exclusion():
    row = garment("Джинсы", Трикотаж="Нет", **{"Промышленная или профессиональная одежда": "Нет"})
    assert engine().classify(extract_features(row))["code"] is None
    assert (
        engine().classify(extract_features({**row, "Деним": "Да", "Вельвет-корд с разрезным ворсом": "Нет"}))[
            "code"
        ]
        == "6203423100"
    )
    assert (
        engine().classify(
            extract_features({**row, "Деним": "Нет", "Вельвет-корд с разрезным ворсом": "Нет"})
        )["code"]
        == "6203423500"
    )


def test_light_knit_real_measurements_boundaries():
    row = garment(
        "Джемпер с воротом поло",
        **{
            "Легкое облегающее изделие": "Да",
            "Петли на 1 см по горизонтали": 12,
            "Петли на 1 см по вертикали": 12,
            "Ворот без разреза": "Да",
        },
    )
    assert engine().classify(extract_features(row))["code"] == "6110201000"
    assert (
        engine().classify(extract_features({**row, "Петли на 1 см по горизонтали": 11}))["code"]
        == "6110209100"
    )
    assert engine().classify(extract_features({**row, "Ворот без разреза": None}))["code"] is None


def test_heavy_wool_threshold_and_actual_percent():
    row = garment("Свитер", "70% шерсть, 30% полиэстер", **{"Масса изделия": "600 г"})
    assert engine().classify(extract_features(row))["code"] == "6110111000"
    assert engine().classify(extract_features({**row, "Масса изделия": "599 г"}))["code"] == "6110113000"
    assert engine().classify(extract_features({**row, "Масса изделия": None}))["code"] is None


@pytest.mark.parametrize(
    "fields,code",
    [
        ({}, "6403999600"),
        ({"Длина стельки": "240 мм"}, "6403999600"),
        ({"Длина стельки": "23.9 см"}, "6403999100"),
        ({"Материал подошвы": "натуральная кожа"}, "6403599500"),
        ({"Пол": "Женский"}, "6403999800"),
        ({"Металлический подносок": "Да"}, "6403400000"),
    ],
)
def test_footwear_positive_and_boundaries(fields, code):
    assert engine().classify(extract_features(shoe(**fields)))["code"] == code


@pytest.mark.parametrize(
    "field",
    [
        "Материал верха",
        "Материал подошвы",
        "Длина стельки",
        "Закрывает лодыжку",
        "Металлический подносок",
        "Спортивная обувь",
        "Домашняя обувь",
        "Союзка с вырезами",
    ],
)
def test_shoe_missing_branch_feature_is_unresolved(field):
    result = engine().classify(extract_features(shoe(**{field: None})))
    assert result["code"] is None and result["missing_input"] and not result["missing_rule"]


def test_shoe_unknown_or_multiple_material_not_guessed():
    assert footwear.material("натуральная кожа и текстиль") is None
    assert engine().classify(extract_features(shoe(**{"Материал верха": "экокожа"})))["code"] is None


@pytest.mark.parametrize(
    "fields,code",
    [
        (
            {
                "Материал верха": "резина",
                "Водонепроницаемая обувь": "Да",
                "Крепление верха к подошве": "литье",
                "Металлический подносок": "Да",
                "Длина стельки": None,
            },
            "6401100000",
        ),
        (
            {
                "Материал верха": "пластмасса",
                "Водонепроницаемая обувь": "Нет",
                "Ремешки прикреплены заклепками": "Нет",
            },
            "6402999600",
        ),
        (
            {
                "Материал верха": "текстиль",
                "Теннисная баскетбольная гимнастическая тренировочная обувь": "Нет",
            },
            "6404199000",
        ),
        (
            {
                "Материал верха": "текстиль",
                "Теннисная баскетбольная гимнастическая тренировочная обувь": "Да",
            },
            "6404110000",
        ),
        ({"Материал подошвы": "дерево"}, "6405100001"),
        (
            {
                "Материал подошвы": "натуральная кожа",
                "Союзка из ремешков": "Да",
                "Высота подошвы и каблука": "3.1 см",
                "Длина стельки": None,
            },
            "6403591100",
        ),
        (
            {
                "Материал подошвы": "натуральная кожа",
                "Союзка из ремешков": "Да",
                "Высота подошвы и каблука": "3 см",
            },
            "6403593500",
        ),
    ],
)
def test_shoe_other_headings_and_technical_branches(fields, code):
    result = engine().classify(extract_features(shoe(**fields)))
    assert result["code"] == code, result["comment"]


@pytest.mark.parametrize(
    "composition",
    [
        "100% хлопок; неизвестный компонент",
        "100% хлопок + микрофибра",
        "100% хлопок и полиэстер",
        "70% хлопок, 40% полиэстер",
        "-100% хлопок",
    ],
)
def test_unparsed_or_inconsistent_composition_never_confirms(composition):
    assert engine().classify(extract_features(garment(composition=composition)))["code"] is None


def test_unimplemented_clause_is_never_ignored():
    card = deepcopy(ALTA["cards"]["6105100000"])
    card["levels"][-1]["description"] += ", со специальным неизвестным покрытием"
    assert CandidateValidator().assess(extract_features(garment()), card).missing_rule
    card = deepcopy(ALTA["cards"]["6403999600"])
    card["levels"][-1]["description"] += ", с неизвестным специальным условием"
    assert CandidateValidator().assess(extract_features(shoe()), card).verdict == "unresolved"


@pytest.mark.parametrize(
    "row",
    [
        garment(**{"Покрытие ткани": "пластмасса"}),
        garment(Конструкция="специальная"),
        shoe(Назначение="ортопедическая"),
    ],
)
def test_explicit_special_input_cannot_be_ignored(row):
    result = engine().classify(extract_features(row))
    assert result["code"] is None and "UNIMPLEMENTED_RULE" in result["reason_categories"]
    assert result["missing_rule"]


def test_cache_record_never_skips_new_competitor():
    e = engine()
    e.sessions = lambda: pytest.fail("Persistent cache must not shortcut discovery")
    e.finder.find = lambda f: ["6105100000", "6105201000"]
    e.client.verify = lambda c: {**deepcopy(ALTA["cards"]["6105100000"]), "code": c}
    result = e.classify(extract_features(garment()))
    assert result["code"] is None and len(result["candidates"]) == 2


def test_tree_missing_closed_children_and_bad_code_fail_closed():
    client = AltaClient(
        httpx.MockTransport(
            lambda r: httpx.Response(
                200,
                text='<li data-source="6105" data-uin="x" class="jstree-closed"></li>'
                if r.url.params.get("tnved")
                else "",
            )
        ),
        interval=0,
    )
    with pytest.raises(SourceUnavailable):
        CandidateFinder(client).find(extract_features(garment()))
    with pytest.raises(SourceUnavailable):
        client.verify("../../other")
    client.close()


def test_tik_only_discovers_and_does_not_verify_codes():
    requests = []

    def response(request):
        requests.append(request)
        return httpx.Response(200, text='<a href="/tnved/code/6105100000/">Результат поиска</a>')

    client = AltaClient(httpx.MockTransport(response), interval=0)
    codes, trace = client.discover_tik(extract_features(garment()))
    assert codes == ["6105100000"] and trace["purpose"] == "DISCOVERY_ONLY"
    assert "хлопок" in requests[0].url.params["srchstr"]
    assert "мужской" in trace["query"]
    with pytest.raises(SourceUnavailable):
        client.verify(codes[0])  # A search result has no full card marker/path.
    client.close()


def test_permanent_original_bytes_and_row_alignment():
    assert hashlib.sha256(base64.b64decode(BASELINE["xlsx_base64"])).hexdigest() == BASELINE["sha256"]
    assert len(BASELINE["rows"]) == 57
    skill = BASELINE["previous_files"][1]
    for source, previous in zip(BASELINE["rows"], skill["rows"], strict=True):
        assert source["Код"] == previous["Код"]


@pytest.mark.parametrize(
    "expected", EXPECTED["rows"], ids=lambda row: str(row["row"]) + "-" + row["source_code"]
)
def test_real_57_semantic_golden(expected):
    source = BASELINE["rows"][expected["row"] - 2]
    result = engine().classify(extract_features(source))
    explanation = f"Breaking regression at row {expected['row']}: {expected['reviewed_decision']}; got {result['code']} {result['comment']}"
    assert result["code"] == expected["code"], explanation
    if expected["status"] == "CONFIRMED":
        assert result["status"] == "Код определён" and result["evidence"]
        assert len([c for c in result["candidates"] if c["verdict"] == "match"]) == 1
        assert all(c["verdict"] == "excluded" for c in result["candidates"] if c["code"] != result["code"])
    else:
        assert result["reason_categories"] == ["MISSING_INPUT"], explanation
        for fragment in expected["required_reason_fragments"]:
            assert fragment in result["comment"], explanation
