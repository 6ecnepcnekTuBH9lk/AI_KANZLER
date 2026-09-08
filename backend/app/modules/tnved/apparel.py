"""Supported clothing conditions; every unrecognised branch fails closed."""

import re

from app.modules.tnved.branch_descriptions import HEADINGS
from app.modules.tnved.conditions import Assessment, code_key, number
from app.modules.tnved.features import boolean
from app.shared.excel import norm

KIND_WORDS = {
    "футболка": ("майк", "фуфайк", "футбол", "тенниск"),
    "рубашка": ("рубаш", "блуз", "сороч"),
    "джемпер": ("джемпер", "пуловер", "кардиган", "свитер"),
    "пиджак": ("пиджак", "блайзер", "блейзер"),
    "брюки": ("брюк", "бридж"),
    "джинсы": ("брюк", "бридж"),
    "шорты": ("шорт",),
    "куртка": ("куртк", "ветровк", "анорак"),
    "пальто": ("пальто", "плащ"),
    "галстук": ("галстук",),
    "носки": ("носк",),
    "шарф": ("шарф", "кашне"),
    "ремень": ("ремни", "пояса"),
}
MATERIAL_WORDS = {
    "хлопок": r"хлопчатобумаж",
    "шерсть": r"шерстян|тонкого волоса животных",
    "кашемир": r"кашемир|кашмирск",
    "шелк": r"шелков",
    "лен": r"льнян|рами",
    "синтетические": r"синтетическ",
    "искусственные": r"искусствен",
    "химические": r"химическ",
}
MATERIAL_DESCRIPTIONS = {
    "из искусственных нитей",
    "из льняных волокон или волокна рами",
    "из пряжи из тонкого волоса кашмирской козы",
    "из синтетических нитей",
    "из химических нитей",
    "из хлопчатобумажной пряжи",
    "из шелковых нитей или пряжи из шелковых отходов",
    "из шерстяной пряжи или пряжи из тонкого волоса животных",
    "из шерстяной пряжи или пряжи из тонкого волоса животных или из химических нитей",
    "из шерстяной пряжи",
    "из прочих текстильных материалов",
}
PRODUCT_DESCRIPTIONS = {
    "костюмы",
    "комплекты",
    "пиджаки и блайзеры",
    "брюки, комбинезоны с нагрудниками и лямками, бриджи и шорты",
    "брюки и бриджи",
    "комбинезоны с нагрудниками и лямками",
    "шорты",
    "колготы прочие",
    "гольфы",
    "женские чулки",
    "части",
    "предметы одежды",
    "перчатки, рукавицы и митенки",
    "пояса, ремни, портупеи и патронташи",
    "шали, шарфы, кашне, мантильи, вуали и аналогичные изделия",
    "галстуки, галстуки-бабочки и шейные платки",
}


def predicate(f, node, source, heading=False):
    text = norm(node["description"]).strip(" :")
    result = Assessment()
    residual = bool(re.search(r"\bпроч(?:ие|ая|ий|ее|их)\b", text))
    # Historical wording can coexist with a current description. Do not interpret dates as measurements.
    if text.startswith("[с ") and "/[по " in text:
        text = re.sub(r"^\[с [^]]+\]\s*", "", text.split("/[по ")[0])
    if heading:
        expected = (
            "42" if f.kind == "ремень" else "61" if f.knit is True else "62" if f.knit is False else None
        )
        result.check(
            None if expected is None else code_key(node).startswith(expected),
            "группа по материалу / трикотажу",
            source,
        )
        if f.kind == "ремень":
            result.check(
                f.material == "натуральная кожа" if f.material else None, "натуральная кожа ремня", source
            )
        elif code_key(node) != "6117":
            kinds = {k for k, stems in KIND_WORDS.items() if any(stem in text for stem in stems)}
            result.check(f.kind in kinds if f.kind else None, "вид изделия в товарной позиции", source)
        if "муж" in text and "жен" not in text:
            result.check(f.gender == "мужской" if f.gender else None, "мужской пол", source)
        elif "жен" in text and "муж" not in text:
            result.check(f.gender == "женский" if f.gender else None, "женский пол", source)
        if text != norm(HEADINGS.get(code_key(node), "")):
            result.check(
                None, "не проверена новая формулировка товарной позиции: " + text, source, implemented=False
            )
        return result, False
    if re.fullmatch(r"(?:для )?(?:мужчин|женщин)(?: или (?:мальчиков|девочек))?", text):
        gender = "мужской" if "муж" in text else "женский"
        return result.check(f.gender == gender if f.gender else None, "пол: " + gender, source), False
    if text in MATERIAL_DESCRIPTIONS:
        groups = {g for g, pattern in MATERIAL_WORDS.items() if re.search(pattern, text)}
        if groups:
            if "шерсть" in groups and "тонкого волоса" in text:
                groups.add("кашемир")
            if "химические" in groups:
                groups |= {"синтетические", "искусственные"}
            value = f.material in groups if f.material else None
            if f.material == "шерсть и тонкий волос" and groups & {"шерсть", "кашемир"}:
                value = True if {"шерсть", "кашемир"} <= groups else None
            if (
                f.material == "химические"
                and "химические" not in groups
                and groups & {"синтетические", "искусственные"}
            ):
                value = None
            return result.check(value, "классифицирующий материал: " + text, source), residual
        if residual and text == "из прочих текстильных материалов":
            return result.check(
                f.material is not None or None, "определён материал для остаточной ветви", source
            ), True
    if text in ("прочие", "прочая", "принадлежности прочие", "прочие принадлежности к одежде"):
        return result, True
    if "производственные и профессиональные" in text:
        return result.check(
            boolean(f.details.get("промышленная или профессиональная одежда")),
            "промышленная или профессиональная одежда",
            source,
        ), residual
    if text == "из денима, или джинсовой ткани":
        return result.check(
            boolean(f.details.get("деним")),
            "деним по определению ткани Alta (торгового названия «джинсы» недостаточно)",
            source,
        ), False
    if "вельвет-корда с разрезным ворсом" in text:
        return result.check(
            boolean(f.details.get("вельвет-корд с разрезным ворсом")),
            "вельвет-корд с разрезным ворсом",
            source,
        ), False
    if "легкие тонкие джемперы" in text:
        light = boolean(f.details.get("легкое облегающее изделие"))
        horizontal = number(f.details.get("петли на 1 см по горизонтали"))
        vertical = number(f.details.get("петли на 1 см по вертикали"))
        collar = boolean(f.details.get("ворот поло или высокий ворот"))
        if collar is None and re.search(
            r"ворот\w* поло|высок\w* ворот", f.details.get("описание товара", "")
        ):
            collar = True
        result.check(light, "легкое облегающее изделие по пояснению 6110", source)
        result.check(
            horizontal >= 12 if horizontal is not None else None,
            "не менее 12 петель на 1 см по горизонтали",
            source,
        )
        result.check(
            vertical >= 12 if vertical is not None else None,
            "не менее 12 петель на 1 см по вертикали",
            source,
        )
        result.check(collar, "ворот поло или высокий одинарный/двойной ворот", source)
        result.check(
            boolean(f.details.get("ворот без разреза")), "ворот без разреза по пояснению 6110", source
        )
        return result, False
    if "массой" in text and "600" in text and "50" in text and "шерст" in text:
        mass = number(f.details.get("масса изделия"), "г")
        result.check(mass >= 600 if mass is not None else None, "масса одного изделия не менее 600 г", source)
        wool = dict(f.composition).get("шерсть", 0)
        result.check(
            wool >= 50 if f.composition_total >= 99.5 and not f.unknown_fibers else None,
            "не менее 50 мас.% шерсти в составе",
            source,
        )
        subtype = norm(f.details.get("вид трикотажного изделия"))
        title = f.details.get("описание товара", "")
        value = (
            True
            if re.search(r"свитер|пуловер", subtype or title)
            else False
            if "кардиган" in (subtype or title)
            else None
        )
        result.check(value, "свитер или пуловер (уточнить подвид джемпера)", source)
        return result, False
    if "компрессионные" in text:
        return result.check(
            boolean(f.details.get("компрессионные изделия")),
            "компрессионные изделия с распределенным давлением",
            source,
        ), False
    if text == "трикотажные машинного или ручного вязания, эластичные или прорезиненные":
        elastic, rubber = (
            boolean(f.details.get("эластичное полотно")),
            boolean(f.details.get("резиновая нить")),
        )
        value = True if True in (elastic, rubber) else False if elastic is False and rubber is False else None
        return result.check(value, "эластичные или прорезиненные принадлежности", source), False
    # Exact product-only branches: evaluate intermediate levels as well as leaves.
    if text in PRODUCT_DESCRIPTIONS:
        kinds = {k for k, stems in KIND_WORDS.items() if any(s in text for s in stems)}
        known_other = any(
            s in text
            for s in (
                "костюм",
                "комплект",
                "комбинезон",
                "колгот",
                "чулки",
                "гольфы",
                "перчатк",
                "рукавиц",
                "части",
                "предметы одежды",
            )
        )
        if kinds or known_other:
            return result.check(f.kind in kinds if f.kind else None, "вид изделия: " + text, source), residual
    return result.check(None, "правило ветви: " + text, source, implemented=False), residual
