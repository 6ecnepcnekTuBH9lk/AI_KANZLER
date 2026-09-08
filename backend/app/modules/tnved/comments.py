"""Compact next clarification for Excel; classification evidence stays untouched.

The comment asks for the first useful missing discriminator. It is not a claim
that answering it alone will prove the code: the engine rechecks every condition.
Never render candidate descriptions or internal exception text into this field.
"""


def user_comment(features, result):
    if result.get("code") and result.get("status") == "Код определён":
        return ""
    status = result.get("status")
    if status == "Уже имел код":
        return "Исходный код сохранён без проверки."
    if status == "Исходный код не подтверждён":
        original = result.get("original_code")
        return (
            "Исходная формула сохранена; код не подтверждён."
            if isinstance(original, str) and original.startswith("=")
            else "Исходный код сохранён, но не подтверждён."
        )
    if status == "Техническая ошибка":
        return "Не удалось подтвердить код на Alta. Повторите проверку после восстановления доступа."
    if features.conflicts:
        return "В описании товара есть противоречия. Уточните согласованные характеристики изделия."

    missing = " ".join(
        x
        for x in result.get("missing_input", features.missing)
        if not x.startswith("исключение альтернативы:")
    ).lower()
    if features.kind != "обувь" and features.unknown_fibers:
        if all("микрофибр" in x for x in features.unknown_fibers):
            return (
                "Состав указан недостаточно подробно: «микрофибра» не раскрывает материал волокна "
                "(например, полиэстер или полиамид)."
            )
        return "Состав указан недостаточно подробно: необходимо уточнить тип и долю нераспознанных волокон."
    basics = []
    if features.kind is None:
        basics.append("вид изделия")
    if "пол изделия" in features.missing:
        basics.append("пол изделия")
    if "признак трикотажа" in features.missing:
        basics.append("является ли изделие трикотажным")
    if basics:
        return "Недостаточно данных для однозначного кода: уточните " + ", ".join(basics) + "."
    if features.kind == "обувь":
        materials = [
            label
            for key, label in (("материал верха", "материал верха"), ("материал подошвы", "материал подошвы"))
            if key not in features.details and key in missing
        ]
        if materials:
            return "Недостаточно данных для кода обуви: укажите " + " и ".join(materials) + "."
        if "длина стельки" in missing:
            description = "обуви"
            if (
                features.details.get("вид обуви") == "лофер"
                and features.gender == "мужской"
                and features.details.get("материал верха") == "натуральная замша"
                and features.details.get("материал подошвы") == "резина"
            ):
                description = "мужских лоферов с верхом из натуральной замши и подошвой из резины"
            return "Недостаточно данных для полного кода: не указана длина стельки " + description + "."
        if missing:
            return "Недостаточно данных для полного кода обуви: необходимо уточнить конструкцию и назначение."
    if "деним" in missing:
        return (
            "Недостаточно данных для однозначного кода: необходимо подтвердить, "
            "изготовлены ли брюки из денима (джинсовой ткани)."
        )
    if "промышленная или профессиональная одежда" in missing:
        return "Недостаточно данных для полного кода: уточните, является ли изделие производственной или профессиональной одеждой."
    if features.kind == "джемпер" and any(x in missing for x in ("петель", "ворот", "облегающее", "вязание")):
        garment = "хлопкового джемпера" if features.material == "хлопок" else "джемпера"
        return f"Недостаточно данных для полного кода {garment}: необходимо уточнить конструкцию и вид вязки изделия."
    if "полный процентный состав" in missing:
        return "Недостаточно данных для полного кода: укажите полный процентный состав основного изделия."
    if result.get("missing_rule"):
        return (
            "Для полного кода требуется проверка специалистом: указанная конструкция пока не поддерживается."
        )
    return (
        "Недостаточно данных для однозначного кода: требуется уточнение характеристик изделия специалистом."
    )
