import hashlib
import json
import re
from dataclasses import asdict, dataclass, field

from app.shared.excel import norm

MATERIALS = {
    "хлопок": ("хлоп", "cotton"),
    "шерсть": ("шерст", "wool"),
    "кашемир": ("кашемир", "cashmere"),
    "шелк": ("шелк", "silk"),
    "лен": ("лен", "льн", "linen"),
    "искусственные": ("лиоцелл", "вискоз", "модал", "тенсел", "lyocell", "viscose", "modal", "ацетат"),
    "синтетические": (
        "полиэстер",
        "полиамид",
        "эластан",
        "спандекс",
        "эластомультиэстер",
        "полиэфир",
        "акрил",
        "нейлон",
        "polyester",
        "elastane",
        "polyamide",
    ),
}
KINDS = {
    "футболка": ("футбол", "тенниск"),
    "рубашка": ("рубаш", "сороч"),
    "джемпер": ("джемпер", "пуловер", "свитер", "кардиган", "толстов", "свитшот"),
    "джинсы": ("джинс",),
    "брюки": ("брюк",),
    "шорты": ("шорт",),
    "пиджак": ("пиджак", "блейзер"),
    "куртка": ("куртк", "ветровк", "анорак"),
    "пальто": ("полупальто", "пальто", "плащ"),
    "галстук": ("галстук",),
    "обувь": ("обув", "лофер", "ботин", "туфл", "кроссов", "сапог", "сандал"),
    "носки": ("носк",),
    "шарф": ("шарф",),
    "ремень": ("ремень",),
}


@dataclass
class Features:
    kind: str | None
    gender: str | None
    knit: bool | None
    composition: list[tuple[str, float]]
    material: str | None
    main_text: str
    details: dict = field(default_factory=dict)
    missing: list[str] = field(default_factory=list)

    @property
    def signature(self):
        data = asdict(self)
        # Main material text is normalized semantically; retain unknown composition to avoid unsafe merging.
        if self.composition and self.material is not None:
            data.pop("main_text")
        return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def extract_features(row):
    r = {norm(k): v for k, v in row.items()}
    title = norm(str(r.get("номенклатура", "")) + " " + str(r.get("наименование", "")))
    kinds = [kind for kind, stems in KINDS.items() if any(s in title for s in stems)]
    if "джинсы" in kinds and "брюки" in kinds:
        kinds.remove("брюки")
    kind = kinds[0] if len(kinds) == 1 else None
    gender_text = norm(r.get("пол"))
    gender = (
        "мужской"
        if "муж" in gender_text
        else "женский"
        if "жен" in gender_text
        else "детский"
        if "дет" in gender_text
        else None
    )
    knit_text = norm(r.get("трикотаж"))
    knit = True if knit_text in ("да", "true", "1") else False if knit_text in ("нет", "false", "0") else None
    composition_text = norm(r.get("состав"))
    main = re.split(r"подкладк|наполнител|утеплител|отделк|стельк|подошв", composition_text)[0].strip(" ;:,")
    parts = re.findall(r"(\d+(?:[.,]\d+)?)\s*%\s*([^\d%;]+)|([^\d%;,:]+)\s*(\d+(?:[.,]\d+)?)\s*%", main)
    amounts = {}
    unknown = []
    for before, mat_after, mat_before, after in parts:
        name = mat_after or mat_before
        value = float((before or after).replace(",", "."))
        material = next((m for m, aliases in MATERIALS.items() if any(a in name for a in aliases)), None)
        if material:
            amounts[material] = amounts.get(material, 0) + value
        else:
            unknown.append(name.strip())
    material = None
    if amounts and not unknown and abs(sum(amounts.values()) - 100) <= 0.5:
        # A plurality can dominate; there is no universal >50% requirement (Alta, section XI).
        # Equal group weights remain unresolved until position-specific notes exclude alternatives.
        winners = [m for m, v in amounts.items() if v == max(amounts.values())]
        material = winners[0] if len(winners) == 1 else None
    missing = []
    if kind is None:
        missing.append("однозначный вид изделия")
    if gender is None:
        missing.append("пол / возрастная группа")
    if knit is None and kind != "обувь":
        missing.append("признак трикотажа")
    if material is None and kind != "обувь":
        missing.append("однозначный классифицирующий материал и полный процентный состав основного изделия")
    details = {"описание товара": title}
    for key in (
        "материал верха",
        "материал подошвы",
        "закрывает лодыжку",
        "длина стельки",
        "конструкция",
        "назначение",
        "плотность",
        "линия",
        "длина рукава",
    ):
        if r.get(key) is not None:
            details[key] = norm(r[key])
    if kind == "обувь":
        upper = re.search(r"(?:верх|основной материал)\s*[:\-]\s*([^;]+)", composition_text)
        sole = re.search(r"подошва\s*[:\-]\s*([^;]+)", composition_text)
        if upper:
            details.setdefault("материал верха", upper[1])
        if sole:
            details.setdefault("материал подошвы", sole[1])
        for key in (
            "материал верха",
            "материал подошвы",
            "закрывает лодыжку",
            "длина стельки",
            "конструкция",
            "назначение",
        ):
            if key not in details:
                missing.append(key)
        details["вид обуви"] = title
    # Conflicting explicit construction must not be ignored.
    if knit is False and re.search(r"трикотажн|вязан", title):
        missing.append("согласование противоречия: наименование и признак трикотажа")
    return Features(kind, gender, knit, sorted(amounts.items()), material, main, details, missing)
