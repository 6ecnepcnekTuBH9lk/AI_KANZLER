import re
from datetime import UTC, datetime

from app.core.exceptions import SourceUnavailable
from app.modules.tnved.alta import CandidateFinder
from app.shared.excel import norm
from app.shared.models import TnvedCache


def valid_code(code):
    return isinstance(code, str) and re.fullmatch(r"[0-9]{10}", code) is not None


class CandidateValidator:
    """Three-valued validation: match, excluded, unresolved. Unknown is never a match."""

    def validate(self, features, evidence):
        if not valid_code(evidence["code"]):
            return "unresolved"
        levels = evidence["levels"][2:]  # Exclude generic section/chapter descriptions.
        text = norm(" ".join(x["description"] for x in levels))
        f = features
        if f.kind == "обувь":
            return "unresolved"  # All technical shoe conditions need a position-specific verified rule.
        if "жен" in text and "муж" not in text and f.gender == "мужской":
            return "excluded"
        if "муж" in text and "жен" not in text and f.gender == "женский":
            return "excluded"
        if "дет" in text and f.gender != "детский" and not any(x in text for x in ("муж", "жен")):
            return "excluded"
        groups = {
            "хлопок": ["хлоп"],
            "шерсть": ["шерст"],
            "кашемир": ["кашемир"],
            "шелк": ["шелк"],
            "лен": ["льн"],
            "искусственные": ["искусствен"],
            "синтетические": ["синтетическ"],
        }
        leaf_text = norm(" ".join(x["description"] for x in levels[1:]))
        material_groups = {g for g, words in groups.items() if any(w in leaf_text for w in words)}
        if (
            material_groups
            and f.material not in material_groups
            and not ("химическ" in leaf_text and f.material in ("искусственные", "синтетические"))
        ):
            return "excluded"
        if "химическ" in leaf_text and f.material not in ("искусственные", "синтетические"):
            return "excluded"
        kind_words = {
            "футболка": ("майк", "фуфайк", "футбол", "тенниск"),
            "рубашка": ("рубаш", "блуз"),
            "джемпер": ("джемпер", "пуловер", "кардиган", "свитер"),
            "пиджак": ("пиджак", "блейзер"),
            "брюки": ("брюк",),
            "джинсы": ("брюк", "деним"),
            "шорты": ("шорт",),
            "куртка": ("куртк", "ветровк", "анорак"),
            "пальто": ("пальто", "плащ"),
            "галстук": ("галстук",),
            "носки": ("носк",),
            "шарф": ("шарф",),
            "ремень": ("ремн",),
        }
        if not any(w in text for w in kind_words.get(f.kind, ())):
            return "excluded"
        # A child describing a different garment excludes the general heading's broad match.
        other_types = {"пиджак": "пиджак", "брюк": "брюки", "шорт": "шорты", "костюм": "костюм"}
        leaf = norm(levels[-1]["description"]) if levels else ""
        for stem, kind in other_types.items():
            if stem in leaf and f.kind not in (kind, "джинсы" if kind == "брюки" else kind):
                return "excluded"
        material_proven = f.material in material_groups or (
            "химическ" in leaf_text and f.material in ("искусственные", "синтетические")
        )
        # Residual "прочие" branches are not resolved merely by largest percentage.
        if not material_proven:
            return "unresolved"
        if "прочие" in leaf or re.search(
            r"\d|массо|плотност|ручного|ворс|махров|вышив|специальн|профессион|деним|промышлен", leaf_text
        ):
            return "unresolved"
        if f.gender == "детский":
            return "unresolved"
        expected_chapter = "61" if f.knit else "62"
        if not evidence["code"].startswith(expected_chapter):
            return "unresolved"
        return "match"


class ClassificationEngine:
    def __init__(self, client, sessions=None):
        self.client, self.sessions = client, sessions
        self.finder, self.validator = CandidateFinder(client), CandidateValidator()
        self.memo = {}

    def classify(self, features):
        signature = features.signature
        if signature in self.memo:
            return self.memo[signature]
        result = {
            "code": None,
            "status": "Требуется уточнение",
            "comment": "",
            "evidence": None,
            "candidates": [],
        }
        if features.missing:
            result["comment"] = (
                "Недостаточно данных для однозначного определения кода: " + "; ".join(features.missing) + "."
            )
        else:
            try:
                # Reuse only same-day verified evidence, not an unbounded stale code cache.
                cached = None
                if self.sessions:
                    with self.sessions() as db:
                        cached = db.get(TnvedCache, signature)
                if cached and cached.verified_at.date() == datetime.now(UTC).date():
                    evidence = self.client.verify(cached.code)
                    if self.validator.validate(features, evidence) == "match":
                        result.update(code=cached.code, status="Код определён", evidence=evidence)
                if result["code"] is None:
                    matches, unresolved = [], []
                    for code in self.finder.find(features):
                        evidence = self.client.verify(code)
                        verdict = self.validator.validate(features, evidence)
                        if verdict != "excluded":
                            result["candidates"].append(
                                {"code": code, "description": evidence["description"], "verdict": verdict}
                            )
                        if verdict == "match":
                            matches.append(evidence)
                        elif verdict == "unresolved":
                            unresolved.append(code)
                    if len(matches) == 1 and not unresolved:
                        result.update(code=matches[0]["code"], status="Код определён", evidence=matches[0])
                    else:
                        result["comment"] = (
                            "Найдено несколько возможных позиций или не проверены дополнительные условия: "
                            "уточните конструкцию, назначение и характеристики материала по описаниям кандидатов Alta.ru."
                            if result["candidates"]
                            else "По указанным характеристикам однозначный полный код на Alta.ru не найден."
                        )
                if result["code"] and self.sessions:
                    with self.sessions.begin() as db:
                        db.merge(
                            TnvedCache(
                                signature=signature,
                                code=result["code"],
                                evidence=result["evidence"],
                                description=result["evidence"]["description"],
                            )
                        )
            except SourceUnavailable as exc:
                result.update(status="Техническая ошибка", comment=exc.message)
        self.memo[signature] = result
        return result
