import re
from copy import deepcopy
from datetime import UTC, datetime

from app.core.exceptions import SourceUnavailable
from app.modules.tnved import apparel, footwear
from app.modules.tnved.alta import CandidateFinder
from app.modules.tnved.conditions import Assessment, PathContext
from app.modules.tnved.features import boolean
from app.shared.models import TnvedCache


def valid_code(code):
    return isinstance(code, str) and re.fullmatch(r"[0-9]{10}", code) is not None


def input_limitations(features):
    """Explicit special input must not disappear behind an otherwise matching ordinary path."""
    limits = []
    if features.age in ("детский", "младенец"):
        limits.append("классификация детской одежды 6111/6209 и проверка роста пока не реализованы")
    if features.details.get("конструкция"):
        limits.append(
            "не разобрана конструкция из свободного текста; нужны поддерживаемые структурированные признаки"
        )
    purpose = features.details.get("назначение")
    if purpose and purpose not in (
        "повседневная",
        "деловая",
        "лыжи",
        "беговые лыжи",
        "сноуборд",
        "бег",
        "теннис",
    ):
        limits.append("не реализовано правило специального назначения: " + purpose)
    if features.kind != "обувь":
        for key in ("покрытие ткани", "ворс", "махровое полотно", "вышивка"):
            value = features.details.get(key)
            if value is not None and boolean(value) is not False:
                limits.append("не реализована проверка влияния признака на основной материал/позицию: " + key)
    return limits


class CandidateValidator:
    """Unknown never matches. Context must include every discovered current card."""

    def assess(self, features, evidence, context=None):
        if not valid_code(evidence.get("code")) or len(evidence.get("levels", [])) < 4:
            return Assessment().check(
                None, "полный путь к десятизначному коду", evidence.get("url", ""), implemented=False
            )
        predicate = footwear.predicate if features.kind == "обувь" else apparel.predicate
        context = context or PathContext([evidence], predicate)
        return context.assess(features, evidence)

    def validate(self, features, evidence):
        return self.assess(features, evidence).verdict


class ClassificationEngine:
    def __init__(self, client, sessions=None):
        self.client, self.sessions = client, sessions
        self.finder, self.validator = CandidateFinder(client), CandidateValidator()
        self.memo = {}

    def classify(self, features):
        signature = features.signature
        if signature in self.memo:
            return deepcopy(self.memo[signature])
        result = {
            "code": None,
            "status": "Требуется уточнение",
            "comment": "",
            "evidence": None,
            "candidates": [],
            "missing_input": list(features.missing),
            "missing_rule": input_limitations(features),
            "reason_categories": [],
            "source_evidence": [],
            "confirmation": "",
        }
        if features.conflicts:
            result["reason_categories"] = ["CONFLICTING_INPUT"]
            result["comment"] = "Необходимо устранить: " + "; ".join(features.conflicts) + "."
        else:
            try:
                # Persistent cache is only an audit record. Never bypass current discovery,
                # verification of competitors or the current policy on a cache hit.
                codes = self.finder.find(features)
                result["discovery"] = getattr(self.finder, "discovery", [])
                cards = [self.client.verify(code) for code in codes]
                if hasattr(self.client, "explanations") and cards:
                    result["source_evidence"] = self.client.explanations(features, cards)
                context = PathContext(
                    cards, footwear.predicate if features.kind == "обувь" else apparel.predicate
                )
                matches, unresolved = [], []
                for card in cards:
                    decision = self.validator.assess(features, card, context)
                    if features.missing and decision.verdict == "match":
                        decision.check(None, "; ".join(features.missing), card["url"])
                    if result["missing_rule"] and decision.verdict == "match":
                        for limit in input_limitations(features):
                            decision.check(None, limit, card["url"], implemented=False)
                    candidate = {
                        **decision.serialize(),
                        "code": card["code"],
                        "description": card["description"],
                        "url": card["url"],
                        "evidence": card,
                    }
                    result["candidates"].append(candidate)
                    if decision.verdict == "match":
                        matches.append(card)
                    elif decision.verdict == "unresolved":
                        unresolved.append(card["code"])
                        for key in ("missing_input", "missing_rule"):
                            result[key].extend(x for x in getattr(decision, key) if x not in result[key])
                if len(matches) == 1 and not unresolved and not features.missing:
                    result.update(
                        code=matches[0]["code"],
                        status="Код определён",
                        evidence=matches[0],
                        confirmation="Актуальная карточка и полный путь проверены; все альтернативы исключены; неразрешённых условий нет.",
                    )
                    result["missing_input"] = []
                    result["missing_rule"] = []
                else:
                    if not cards:
                        result["missing_rule"].append(
                            "не определена поддерживаемая товарная позиция или не найдены листья дерева Alta"
                        )
                    if result["missing_input"]:
                        result["reason_categories"].append("MISSING_INPUT")
                    if result["missing_rule"]:
                        result["reason_categories"].append("UNIMPLEMENTED_RULE")
                    if len(matches) > 1:
                        result["reason_categories"].append("AMBIGUOUS_CANDIDATES")
                    if not result["reason_categories"]:
                        result["reason_categories"] = ["NO_MATCHING_BRANCH"]
                    # Predecessor diagnostics are shown in each candidate; request only concrete facts.
                    facts = [
                        x for x in result["missing_input"] if not x.startswith("исключение альтернативы:")
                    ]
                    messages = []
                    if facts:
                        messages.append(
                            "Для однозначного выбора необходимо уточнить: " + "; ".join(dict.fromkeys(facts))
                        )
                    if result["missing_rule"]:
                        messages.append("Ограничение классификатора: " + "; ".join(result["missing_rule"]))
                    if not messages:
                        messages.append(
                            "Не доказана единственная подходящая ветвь Alta; см. условия кандидатов"
                        )
                    result["comment"] = ". ".join(messages) + "."
                if result["code"] and self.sessions:
                    with self.sessions.begin() as db:
                        db.merge(
                            TnvedCache(
                                signature=signature,
                                code=result["code"],
                                evidence=result["evidence"],
                                description=result["evidence"]["description"],
                                verified_at=datetime.now(UTC),
                            )
                        )
            except SourceUnavailable as exc:
                result.update(
                    code=None,
                    evidence=None,
                    status="Техническая ошибка",
                    comment=exc.message,
                    reason_categories=["SOURCE_UNAVAILABLE"],
                )
        self.memo[signature] = deepcopy(result)
        return result
