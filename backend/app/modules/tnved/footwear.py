"""Conservative 6401–6405 predicates. Code numbers are discovered from Alta, not mapped here."""

import re

from app.modules.tnved.conditions import Assessment, code_key, number
from app.modules.tnved.features import boolean
from app.shared.excel import norm

# Reviewed branch texts from current Alta 6401–6405. This is a grammar guard,
# not a product-to-code table: new/changed conditions must never slip through
# just because a known material word also occurs in the description.
SUPPORTED_DESCRIPTIONS = {
    "24 см или более",
    "менее 24 см",
    "мужская",
    "женская",
    "обувь прочая",
    "прочая",
    "прочая обувь",
    "прочая, с длиной стельки",
    "водонепроницаемая обувь с подошвой и с верхом из резины или пластмассы, верх которой не крепится к подошве и не соединяется с ней ни ниточным, ни шпилечным, ни гвоздевым, ни винтовым, ни заклепочным, ни каким-либо другим аналогичным способом",
    "обувь с подошвой из резины, пластмассы, натуральной или композиционной кожи и с верхом из натуральной кожи",
    "обувь с подошвой из резины, пластмассы, натуральной или композиционной кожи и с верхом из текстильных материалов",
    "прочая обувь с подошвой и с верхом из резины или пластмассы",
    "ботинки для сноуборда",
    "закрывающая лодыжку",
    "закрывающая лодыжку, но не закрывающая колено",
    "закрывающая лодыжку, но не часть икры, с длиной стельки",
    "комнатные туфли и прочая домашняя обувь",
    "лыжные ботинки и беговая лыжная обувь",
    "лыжные ботинки, беговая лыжная обувь и ботинки для сноуборда",
    "обувь с верхом из ремешков или полосок, прикрепленных к подошве заклепками",
    "обувь с защитным металлическим подноском",
    "обувь с защитным металлическим подноском прочая",
    "обувь с подошвой из натуральной или композиционной кожи",
    "обувь с подошвой из натуральной кожи и верхом из ремешков из натуральной кожи, проходящих через подъем и охватывающих большой палец стопы",
    "обувь с подошвой из натуральной кожи прочая",
    "обувь с подошвой из резины или пластмассы",
    "обувь с союзкой из ремешков или имеющая одну или более перфораций",
    "обувь с союзкой из ремешков или имеющая одну или несколько перфораций",
    "обувь, которая не может быть идентифицирована как мужская или женская обувь",
    "с верхом из натуральной или композиционной кожи",
    "с верхом из пластмассы",
    "с верхом из резины",
    "с верхом из текстильных материалов",
    "с защитным металлическим подноском",
    "с основанием или платформой из дерева, без внутренней стельки",
    "с подошвой и каблуком высотой более 3 см",
    "с подошвой из дерева или пробки",
    "с подошвой из других материалов",
    "с подошвой из прочих материалов",
    "с подошвой из резины, пластмассы, натуральной или композиционной кожи",
    "спортивная обувь",
    "спортивная обувь; обувь для тенниса, баскетбола, гимнастики, тренировочная и аналогичная обувь",
}


def material(value):
    text = norm(value)
    patterns = {
        "композиционная кожа": r"композиционн\w* кож",
        "натуральная кожа": r"натуральн\w* (?:кож|замш)|\bзамша\b",
        "резина": r"резин|каучук|\brubber\b",
        "пластмасса": r"пластмасс|полиуретан|\bпвх\b|\bэва\b",
        "текстиль": r"текстил",
        "дерево": r"дерев",
        "пробка": r"пробк",
    }
    found = [group for group, pattern in patterns.items() if re.search(pattern, text)]
    if len(found) != 1:
        return None
    remainder = re.sub("(?:" + patterns[found[0]] + r")\w*", "", text)
    # Unknown coatings and blended materials can change the external surface.
    remainder = re.sub(r"100\s*%|[\s(),]", "", remainder)
    return found[0] if not remainder else None


def allowed_materials(text):
    result = set()
    for key, pattern in {
        "натуральная кожа": r"натуральн",
        "композиционная кожа": r"композиционн",
        "резина": r"резин",
        "пластмасса": r"пластмасс",
        "текстиль": r"текстильн",
        "дерево": r"дерев",
        "пробка": r"пробк",
    }.items():
        if re.search(pattern, text):
            result.add(key)
    return result


def predicate(f, node, source, heading=False):
    text = norm(node["description"])
    result = Assessment()
    if text not in SUPPORTED_DESCRIPTIONS:
        return result.check(None, "правило обувной ветви: " + text, source, implemented=False), False
    residual = bool(re.search(r"\bпроч(?:ая|ие|их)|других материалов", text))
    if "комнатные туфли и прочая домашняя обувь" in text:
        residual = False
    recognized = False
    if heading:
        result.check(f.kind == "обувь" if f.kind else None, "вид изделия: обувь", source)
        recognized = True
    # Restrict material extraction to the named part; lining/insoles never stand in for upper/sole.
    shared = re.search(r"с подошвой и с верхом из (.+)", text)
    upper = re.search(r"(?:с верхом|верхом) из (.+?)(?:,| и |$)", text)
    sole = re.search(r"с подошвой из (.+?)(?: и (?:с )?верхом|$)", text)
    if shared:
        upper_text = sole_text = shared[1].split(", верх")[0]
    else:
        upper_text, sole_text = upper[1] if upper else "", sole[1] if sole else ""
    for key, part_text in (("материал верха", upper_text), ("материал подошвы", sole_text)):
        allowed = allowed_materials(part_text)
        if allowed:
            actual = material(f.details.get(key))
            result.check(actual in allowed if actual else None, key + ": " + part_text, source)
            recognized = True
    if "водонепроницаемая" in text:
        result.check(boolean(f.details.get("водонепроницаемая обувь")), "водонепроницаемая обувь", source)
        method = norm(f.details.get("крепление верха к подошве"))
        allowed = ("литье", "формование", "вулканизация")
        excluded = ("ниточный", "шпилечный", "гвоздевой", "винтовой", "заклепочный")
        value = True if method in allowed else False if method in excluded else None
        result.check(
            value,
            "верх не соединён с подошвой ниточным/шпилечным/гвоздевым/винтовым/заклепочным способом",
            source,
        )
        recognized = True
    for stem, key in (
        ("металлическим подноском", "металлический подносок"),
        ("спортивная обувь", "спортивная обувь"),
        ("домашняя обувь", "домашняя обувь"),
    ):
        if stem in text:
            if stem == "спортивная обувь" and "для тенниса" in text:
                continue
            result.check(boolean(f.details.get(key)), key, source)
            recognized = True
    if "для тенниса" in text:
        sport = boolean(f.details.get("спортивная обувь"))
        training = boolean(f.details.get("теннисная баскетбольная гимнастическая тренировочная обувь"))
        value = True if True in (sport, training) else False if sport is False and training is False else None
        result.check(
            value, "спортивная или теннисная/баскетбольная/гимнастическая/тренировочная обувь (6404)", source
        )
        recognized = True
    if "лыжные" in text or "сноуборда" in text:
        purpose = norm(f.details.get("назначение"))
        accepted = {"лыжи", "беговые лыжи"} if "лыжные" in text else set()
        if "сноуборда" in text:
            accepted.add("сноуборд")
        value = (
            purpose in accepted
            if purpose in ("лыжи", "беговые лыжи", "сноуборд", "повседневная", "бег", "теннис")
            else None
        )
        result.check(value, "назначение: " + text, source)
        recognized = True
    if "закрывающая лодыжку" in text:
        result.check(boolean(f.details.get("закрывает лодыжку")), "закрывает лодыжку", source)
        if "не закрывающая колено" in text:
            v = boolean(f.details.get("закрывает колено"))
            result.check(not v if v is not None else None, "не закрывает колено", source)
        if "но не часть икры" in text:
            v = boolean(f.details.get("закрывает икру"))
            result.check(not v if v is not None else None, "не закрывает часть икры", source)
        recognized = True
    if re.fullmatch(r"(?:менее 24 см|24 см или более)", text):
        length = number(f.details.get("длина стельки"), "см")
        value = (length < 24 if text.startswith("менее") else length >= 24) if length is not None else None
        result.check(value, "длина стельки: " + text, source)
        recognized = True
    if text in ("мужская", "женская"):
        result.check(
            f.gender == ("мужской" if text == "мужская" else "женский") if f.gender else None,
            "пол обуви: " + text,
            source,
        )
        recognized = True
    if "не может быть идентифицирована как мужская или женская" in text:
        result.check(
            False if f.gender in ("мужской", "женский") else None,
            "обувь не может быть идентифицирована по полу",
            source,
        )
        recognized = True
    if "с основанием или платформой из дерева, без внутренней стельки" in text:
        result.check(
            boolean(f.details.get("деревянная платформа без внутренней стельки")),
            "деревянная платформа без внутренней стельки",
            source,
        )
        recognized = True
    if "союзкой из ремешков" in text:
        straps, holes = (
            boolean(f.details.get("союзка из ремешков")),
            boolean(f.details.get("союзка с вырезами")),
        )
        value = True if True in (straps, holes) else False if straps is False and holes is False else None
        result.check(value, "союзка из ремешков или с перфорациями", source)
        recognized = True
    if "высотой более 3 см" in text:
        height = number(f.details.get("высота подошвы и каблука"), "см")
        result.check(
            height > 3 if height is not None else None, "высота подошвы и каблука более 3 см", source
        )
        recognized = True
    if "проходящих через подъем и охватывающих большой палец" in text:
        result.check(
            boolean(f.details.get("ремешки через подъем и большой палец")),
            "ремешки из натуральной кожи через подъем и большой палец",
            source,
        )
        recognized = True
    if "прикрепленных к подошве заклепками" in text:
        result.check(
            boolean(f.details.get("ремешки прикреплены заклепками")),
            "верх из ремешков/полосок, прикрепленных заклепками",
            source,
        )
        recognized = True
    if residual and (
        text in ("прочая", "прочая обувь", "обувь прочая", "прочая, с длиной стельки")
        or "из других материалов" in text
        or "из прочих материалов" in text
    ):
        recognized = True
    if not recognized:
        result.check(None, "правило обувной ветви: " + text, source, implemented=False)
    # Heading 6405 and the residual 6402 must exclude previous full headings.
    if heading and code_key(node) == "6405":
        residual = True
    return result, residual
