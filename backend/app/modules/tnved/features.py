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
    "лен": (r"\bлен\b", "льн", "linen"),
    "искусственные": ("лиоцелл", "вискоз", "модал", "lyocell", "viscose", "modal", "ацетат"),
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
        "nylon",
        "spandex",
        "полипропилен",
    ),
}
KINDS = {
    "футболка": ("футбол", "тенниск"),
    "рубашка": ("рубаш", "сороч"),
    "джемпер": ("джемпер", "пуловер", "свитер", "кардиган", "толстов", "свитшот"),
    "джинсы": ("джинс",),
    "брюки": ("брюк",),
    "шорты": ("шорт",),
    "пиджак": ("пиджак", "блейзер", "блайзер"),
    "куртка": ("куртк", "ветровк", "анорак"),
    "пальто": ("полупальто", "пальто", "плащ"),
    "галстук": ("галстук",),
    "обувь": ("обув", "лофер", "ботин", "туфл", "кроссов", "сапог", "сандал"),
    "носки": ("носк",),
    "шарф": ("шарф",),
    "ремень": ("ремень", "ремни"),
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
    age: str | None = None
    components: list[dict] = field(default_factory=list)
    unknown_fibers: list[str] = field(default_factory=list)
    composition_total: float = 0
    tied_materials: list[str] = field(default_factory=list)
    material_rule: dict = field(default_factory=dict)
    parts: dict = field(default_factory=dict)
    conflicts: list[str] = field(default_factory=list)

    @property
    def signature(self):
        data = asdict(self)
        data.pop("parts")
        data["policy"] = "tnved-2026-09-08-v2"
        # Main material text is normalized semantically; retain unknown composition to avoid unsafe merging.
        if self.composition and self.material is not None:
            data.pop("main_text")
        return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def extract_features(row):
    r = {norm(k): v for k, v in row.items() if k is not None}
    product_name = norm(r.get("наименование"))
    for key in ("бренд", "марка (бренд)", "цвет", "артикул", "артикулы", "код"):
        value = norm(r.get(key))
        if value:
            product_name = re.sub(r"(?<!\w)" + re.escape(value) + r"(?!\w)", " ", product_name)
    # Strip declared identity words before semantic extraction too: a brand or
    # colour that happens to resemble another garment must not introduce that kind.
    title = norm(str(r.get("номенклатура") or "") + " " + product_name)
    kinds = [kind for kind, stems in KINDS.items() if any(s in title for s in stems)]
    if "джинсы" in kinds and "брюки" in kinds:
        kinds.remove("брюки")
    kind = kinds[0] if len(kinds) == 1 else None
    gender_text = norm(r.get("пол"))
    conflicts = []
    title_gender = (
        "мужской"
        if re.search(r"\bмуж\w*|\bмальчик", title)
        else "женский"
        if re.search(r"\bжен\w*|\bдевоч", title)
        else None
    )
    gender = "мужской" if "муж" in gender_text else "женский" if "жен" in gender_text else title_gender
    if gender and title_gender and gender != title_gender:
        conflicts.append("противоречие пола в наименовании и колонке Пол")
    age_text = gender_text + " " + title + " " + norm(r.get("возрастная группа"))
    age = (
        "детский"
        if re.search(r"детск|мальчик|девоч|младен", age_text)
        else "взрослый"
        if re.search(r"взросл", age_text)
        else None
    )
    if re.search(r"младен|новорожден", age_text):
        age = "младенец"
    knit_text = norm(r.get("трикотаж"))
    knit = True if knit_text in ("да", "true", "1") else False if knit_text in ("нет", "false", "0") else None
    title_knit = (
        False
        if re.search(r"нетрикотаж|не\s+трикотаж|тканая|тканый", title)
        else True
        if re.search(r"трикотажн|вязан", title)
        else None
    )
    if knit is not None and title_knit is not None and knit != title_knit:
        conflicts.append("противоречие наименования и признака трикотажа")
    knit = knit if knit is not None else title_knit
    composition_text = norm(r.get("состав"))
    sections = split_parts(composition_text)
    main = sections.get("основной", sections.get("верх", ""))
    pattern = r"(\d+(?:[.,]\d+)?)\s*%\s*([^\d%;]+)|([^\d%;,:]+)\s*(\d+(?:[.,]\d+)?)\s*%"
    matches = list(re.finditer(pattern, main))
    parts = [m.groups() for m in matches]
    amounts = {}
    unknown = []
    components = []
    for before, mat_after, mat_before, after in parts:
        name = mat_after or mat_before
        value = float((before or after).replace(",", "."))
        name = name.strip(" ,:;")
        groups = {m for m, aliases in MATERIALS.items() if any(re.search(a, name) for a in aliases)}
        material = next(iter(groups)) if len(groups) == 1 else None
        remainder = name
        if material:
            for alias in MATERIALS[material]:
                remainder = re.sub(alias + r"\w*", " ", remainder)
            remainder = re.sub(
                r"\b(?:натуральн\w*|органическ\w*|волокн\w*|нит\w*|пряж\w*|меринос\w*)\b", " ", remainder
            )
            if re.search(r"\w|[+/]", remainder):
                material = None
        components.append({"name": name, "percent": value, "group": material})
        if material:
            amounts[material] = amounts.get(material, 0) + value
        else:
            unknown.append(name.strip())
    unparsed = re.sub(pattern, "", main).strip(" ,:;")
    if re.search(r"\w|[+/]", unparsed):
        unknown.append("неразобранный состав: " + unparsed)
    total = sum(c["percent"] for c in components)
    material, ties, rule = select_material(amounts, unknown, total)
    missing = list(conflicts)
    if age in ("детский", "младенец"):
        missing.append("рост ребёнка и исключение одежды для детей ростом не более 86 см")
    if kind is None:
        missing.append("однозначный вид изделия")
    if gender is None and kind not in ("галстук", "шарф", "ремень"):
        missing.append("пол изделия")
    if knit is None and kind not in ("обувь", "ремень"):
        missing.append("признак трикотажа")
    if kind not in ("обувь", "ремень"):
        if unknown:
            missing.append("не раскрыт тип волокна: " + ", ".join(unknown))
        elif not components or abs(total - 100) > 0.5:
            missing.append(f"полный процентный состав основного изделия (сумма {total:g}%)")
    semantic = title
    for key in ("бренд", "марка (бренд)", "цвет", "артикул", "артикулы", "код"):
        value = norm(r.get(key))
        if value:
            semantic = re.sub(r"(?<!\w)" + re.escape(value) + r"(?!\w)", " ", semantic)
    details = {"описание товара": " ".join(semantic.split())}
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
        "закрывает колено",
        "масса изделия",
        "деним",
        "промышленная или профессиональная одежда",
        "ворс",
        "махровое полотно",
        "ручное вязание",
        "число петель на 1 см",
        "легкий тонкий трикотаж",
        "водонепроницаемая обувь",
        "металлический подносок",
        "спортивная обувь",
        "домашняя обувь",
        "ремешки на подъеме",
        "союзка из ремешков",
        "союзка с вырезами",
        "крепление верха к подошве",
        "высота каблука",
        "высота подошвы",
        "супинатор",
        "покрытие ткани",
        "вид химических волокон",
        "резиновая нить",
        "кружево",
        "эластичное полотно",
        "вышивка",
        "вельвет-корд с разрезным ворсом",
        "ворот поло или высокий ворот",
        "вид трикотажного изделия",
        "компрессионные изделия",
        "теннисная баскетбольная гимнастическая тренировочная обувь",
        "закрывает икру",
        "деревянная платформа без внутренней стельки",
        "высота подошвы и каблука",
        "ремешки через подъем и большой палец",
        "ремешки прикреплены заклепками",
        "легкое облегающее изделие",
        "петли на 1 см по горизонтали",
        "петли на 1 см по вертикали",
        "ворот без разреза",
    ):
        if r.get(key) is not None:
            details[key] = norm(r[key])
    if kind == "обувь":
        upper = re.search(r"верх\s*[:\-]\s*([^;]+)", composition_text)
        sole = re.search(r"подошва\s*[:\-]\s*([^;]+)", composition_text)
        if upper:
            details.setdefault("материал верха", upper[1])
        if sole:
            details.setdefault("материал подошвы", sole[1])
        for key in (
            "материал верха",
            "материал подошвы",
        ):
            if key not in details:
                missing.append(key)
        details["вид обуви"] = next((s for s in KINDS["обувь"] if s != "обув" and s in title), "обувь")
    if kind == "ремень":
        material = "натуральная кожа" if "натуральная кожа" in main else None
        if not material:
            missing.append("материал ремня")
    return Features(
        kind,
        gender,
        knit,
        sorted(amounts.items()),
        material,
        main,
        details,
        missing,
        age,
        sorted(components, key=lambda c: (c["name"], c["percent"])),
        sorted(unknown),
        total,
        ties,
        rule,
        sections,
        conflicts,
    )


def boolean(value):
    value = norm(value)
    return (
        True
        if value in ("да", "true", "1", "есть")
        else False
        if value in ("нет", "false", "0", "отсутствует")
        else None
    )


def split_parts(text):
    marker = re.compile(
        r"(?P<label>основн\w*(?:\s+(?:ткань|материал))?|верх|подкладк\w*|наполнител\w*|утеплител\w*|отделк\w*|стельк\w*|подошв\w*)\s*[:\-]"
    )
    matches = list(marker.finditer(text))
    if not matches:
        return {
            "основной": re.split(r"\b(?:подкладк|наполнител|утеплител|отделк|стельк|подошв)\w*", text)[
                0
            ].strip(" ;:,")
        }
    parts = {}
    prefix = text[: matches[0].start()].strip(" ;:,")
    if prefix:
        parts["основной"] = prefix
    for i, m in enumerate(matches):
        label = "основной" if m["label"].startswith("основн") else m["label"]
        parts[label] = text[m.end() : matches[i + 1].start() if i + 1 < len(matches) else len(text)].strip(
            " ;:,"
        )
    return parts


def select_material(amounts, unknown, total):
    """Alta XI note 2 and subheading note 2; retain unresolved chemical subtype."""
    rule = {
        "source": "https://www.alta.ru/poyasnenia/R11/",
        "rule": "XI.2(A,B); subheading note 2",
        "groups": {},
    }
    if unknown or not amounts or abs(total - 100) > 0.5:
        return None, [], rule
    chapter = {
        "шелк": 50,
        "шерсть": 51,
        "кашемир": 51,
        "хлопок": 52,
        "лен": 53,
        "синтетические": 55,
        "искусственные": 55,
    }
    chapters = {}
    for group, value in amounts.items():
        chapters[chapter[group]] = chapters.get(chapter[group], 0) + value
    rule["groups"] = chapters
    winners = [c for c, v in chapters.items() if abs(v - max(chapters.values())) < 1e-8]
    selected = max(winners)
    ties = [g for g in amounts if chapter[g] in winners] if len(winners) > 1 else []
    if selected == 55:
        chemical = {g: v for g, v in amounts.items() if chapter[g] == 55}
        if len(chemical) == 1:
            material = next(iter(chemical))
        else:
            largest, smallest = max(chemical, key=chemical.get), min(chemical, key=chemical.get)
            # Sufficient bound: the larger type wins even if split evenly across 54/55.
            material = largest if chemical[largest] > 2 * chemical[smallest] else "химические"
            rule["chemical_detail"] = (
                "тип доказан при любом распределении 54/55"
                if material != "химические"
                else "для разделения искусственных/синтетических нужны нити/штапельные волокна"
            )
    elif selected == 51:
        material = (
            "шерсть и тонкий волос"
            if "кашемир" in amounts and "шерсть" in amounts
            else "кашемир"
            if "кашемир" in amounts
            else "шерсть"
        )
    else:
        material = next(g for g in amounts if chapter[g] == selected)
    return material, ties, rule
