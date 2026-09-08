"""Explicit reviewed decisions. Run only when a rule review intentionally changes the baseline."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "backend/tests/fixtures/tnved"


def main():
    baseline = json.loads((FIXTURE / "baseline.json").read_text(encoding="utf-8"))
    confirmed = {
        10: "6109902000",
        11: "6109902000",
        12: "6109902000",
        16: "6103330000",
        17: "6103430001",
        18: "6103390000",
        19: "6103490001",
        20: "6203399000",
        21: "6203399000",
        22: "6103330000",
        23: "6103430001",
        48: "6215100000",
        49: "6215100000",
        50: "6215100000",
        51: "6201900000",
        52: "6201300000",
        53: "6201400000",
        54: "6201400000",
        55: "6201200000",
    }
    rows = []
    for rownum, source in enumerate(baseline["rows"], 2):
        category, required, reason = (
            "CONFIRMED",
            [],
            "Полный путь соответствует виду, полу, трикотажу и материалу; альтернативы исключены.",
        )
        difference = None
        if rownum in range(2, 10):
            category, required, reason = (
                "SHOE_MATERIALS",
                ["материал верха", "материал подошвы"],
                "Общий состав «натуральная кожа» не описывает отдельно верх и наружную подошву.",
            )
        elif rownum in range(28, 32):
            category, required, reason = (
                "SHOE_CONSTRUCTION",
                ["лодыжку", "длина стельки", "перфорациями"],
                "В структурированном составе распознаны верх из натуральной замши и резиновая подошва; не доказаны длина стельки и конструктивные признаки.",
            )
        elif rownum in (18, 19):
            reason = "TENCEL/тенсел распознан как искусственное целлюлозное волокно; вместе с вискозой 97%. Полный код подтверждён Alta, совпадает со Skill."
        elif rownum in (13, 14, 15):
            category, required, reason = (
                "DENIM_AND_USE",
                ["деним", "профессиональная", "вельвет"],
                "Название «джинсы» не доказывает определение денима, исключение вельвет-корда и производственного назначения.",
            )
        elif rownum in (24, 25, 26, 27):
            category, required, reason = (
                "PROFESSIONAL_USE",
                ["промышленная или профессиональная одежда"],
                "Нельзя исключить производственную/профессиональную ветвь по бренду KANZLER или отсутствию назначения в Excel. Предыдущий Skill сделал недостаточно доказанное предположение; для доказательства по-прежнему не хватает данных.",
            )
            difference = "E"
        elif rownum in range(32, 48):
            category, required, reason = (
                "UNKNOWN_FIBER",
                ["микрофибра"],
                "Микрофибра не раскрывает химический тип волокна; основной состав требует уточнения.",
            )
        elif rownum in (56, 57, 58):
            category, required, reason = (
                "KNIT_DENSITY_AND_COLLAR",
                ["12 петель", "облегающее", "без разреза"],
                "Не проверены признаки лёгкого тонкого трикотажа по P6110: плотность по двум направлениям, облегание и ворот без разреза.",
            )
        elif rownum in (16, 17, 22, 23):
            reason = "Реализовано отсутствовавшее правило: промежуточный вид изделия и материал; у брюк остаточные альтернативы исключены. Совпадает с предыдущим Skill."
        elif rownum in (20, 21):
            reason = "Реализовано отсутствовавшее правило: лён является классифицирующим материалом, исключены все предшествующие материалы у пиджаков. Совпадает с Skill."
        elif rownum == 54:
            reason = "Breaking change объяснён XI.2: шерсть 50%, объединённые химические волокна 50%; при равенстве выбирается последняя группа 54/55. Актуальная ветвь 6201400000 охватывает химические нити. Совпадает со Skill; app_before 6201200000 ошибочен."
        rows.append(
            {
                "row": rownum,
                "source_code": source["Код"],
                "article": source.get("Артикул", source.get("Артикулы")),
                "status": "CONFIRMED" if rownum in confirmed else "UNRESOLVED",
                "code": confirmed.get(rownum),
                "category": category,
                "required_reason_fragments": required,
                "skill_difference_category": difference,
                "reviewed_decision": reason,
            }
        )
    payload = {
        "review_date": "2026-09-08",
        "source_sha256": baseline["sha256"],
        "skill_file": baseline["previous_files"][1]["name"],
        "skill_sha256": baseline["previous_files"][1]["sha256"],
        "skill_provenance": "User confirmed the 23-code file in this task",
        "rows": rows,
    }
    target = FIXTURE / "expected.json"
    if target.exists():
        raise SystemExit(
            "Expected fixture exists. Review the diff and update explicitly; no automatic rebaseline."
        )
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
