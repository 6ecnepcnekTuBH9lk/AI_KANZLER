"""Auditable three-valued predicates and residual branches over live Alta paths."""

import re
from dataclasses import asdict, dataclass, field

from app.shared.excel import norm


@dataclass
class Assessment:
    verdict: str = "match"
    reasons: list[str] = field(default_factory=list)
    missing_input: list[str] = field(default_factory=list)
    missing_rule: list[str] = field(default_factory=list)
    conditions: list[dict] = field(default_factory=list)

    def check(self, value, label, source, *, implemented=True):
        verdict = "unresolved" if value is None else "match" if value else "excluded"
        self.conditions.append({"condition": label, "verdict": verdict, "source": source})
        if verdict == "excluded":
            self.verdict = "excluded"
            self.reasons.append("Противоречие: " + label)
        elif verdict == "unresolved":
            if self.verdict != "excluded":
                self.verdict = "unresolved"
            (self.missing_input if implemented else self.missing_rule).append(label)
        return self

    def merge(self, other):
        if other.verdict == "excluded" or self.verdict == "excluded":
            self.verdict = "excluded"
        elif other.verdict == "unresolved":
            self.verdict = "unresolved"
        for name in ("reasons", "missing_input", "missing_rule", "conditions"):
            getattr(self, name).extend(x for x in getattr(other, name) if x not in getattr(self, name))
        return self

    def serialize(self):
        return asdict(self)


def code_key(level):
    return re.sub(r"\D", "", level["code"])


def number(value, unit=None):
    """Reject ranges, signs and unitless measurements unless a schema supplies units."""
    text = norm(value)
    m = re.fullmatch(r"(\d+(?:[.,]\d+)?)\s*([а-яa-z²/0-9 ]*)", text)
    if not m:
        return None
    amount, suffix = float(m[1].replace(",", ".")), m[2].strip()
    if unit == "см":
        return amount if suffix == "см" else amount / 10 if suffix == "мм" else None
    if unit == "г":
        return amount if suffix == "г" else amount * 1000 if suffix == "кг" else None
    return amount if not suffix else None


class PathContext:
    def __init__(self, cards, predicate):
        self.predicate = predicate
        self.children = {}
        self.order = {}
        for card in cards:
            path = ()
            for node in card["levels"][2:]:
                key = (code_key(node), norm(node["description"]))
                self.children.setdefault(path, {})[key] = (node, card["url"])
                self.order[(path, key)] = min(card["code"], self.order.get((path, key), card["code"]))
                path += (key,)
        self.memo = {}

    def node(self, f, parent, key):
        cache_key = (f.signature, parent, key)
        if cache_key in self.memo:
            return self.memo[cache_key]
        node, source = self.children[parent][key]
        result, residual = self.predicate(f, node, source, len(parent) == 0)
        # A residual is defined by preceding alternatives at this exact level,
        # not by arbitrary leaves or a broad heading that also mentions the item.
        if residual and result.verdict != "excluded":
            preceding = [
                (k, n)
                for k, n in self.children[parent].items()
                if self.order[(parent, k)] < self.order[(parent, key)]
            ]
            if not preceding:
                # Some Alta virtual intermediate nodes have an equal code prefix;
                # without a predecessor proof no catch-all is silently accepted.
                result.check(
                    None,
                    "не установлены предшествующие альтернативы остаточной ветви: " + node["description"],
                    source,
                    implemented=False,
                )
            for sibling, (other, _) in preceding:
                alternative = self.node(f, parent, sibling)
                value = (
                    True
                    if alternative.verdict == "excluded"
                    else False
                    if alternative.verdict == "match"
                    else None
                )
                result.check(value, "исключение альтернативы: " + other["description"], source)
                if value is None:
                    result.missing_input.extend(
                        x for x in alternative.missing_input if x not in result.missing_input
                    )
                    result.missing_rule.extend(
                        x for x in alternative.missing_rule if x not in result.missing_rule
                    )
        self.memo[cache_key] = result
        return result

    def assess(self, f, card):
        result = Assessment()
        path = ()
        for node in card["levels"][2:]:
            key = (code_key(node), norm(node["description"]))
            result.merge(self.node(f, path, key))
            path += (key,)
        return result
