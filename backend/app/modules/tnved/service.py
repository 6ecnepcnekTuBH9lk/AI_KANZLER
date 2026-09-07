from dataclasses import asdict
from pathlib import Path

from app.core.exceptions import InputError, IntegrityError
from app.modules.tnved.alta import AltaClient
from app.modules.tnved.classifier import ClassificationEngine, valid_code
from app.modules.tnved.features import extract_features
from app.modules.tnved.reporting import patch_workbook
from app.shared.excel import norm, read_tables
from openpyxl.utils import get_column_letter


def run(files, options, output_dir, progress, sessions, client_factory=AltaClient):
    if len(files) != 1:
        raise InputError("Загрузите один XLSX для классификации.")
    file = files[0]
    tables = read_tables(file.path)
    formula_cells = {
        (table.sheet, ri, i): cell.value
        for table in read_tables(file.path, data_only=False)
        for ri, row in table.rows
        for i, cell in enumerate(row)
        if isinstance(cell.value, str) and cell.value.startswith("=")
    }
    items, edits, added = [], {}, {}
    progress(5, "Чтение номенклатуры")
    client = client_factory()
    engine = ClassificationEngine(client, sessions)
    try:
        total = sum(len(t.rows) for t in tables)
        for table in tables:
            if table.col("номенклатура", "наименование") is None:
                continue
            code_cols = [i for i, h in enumerate(table.headers) if re_code_header(h)]
            if len(code_cols) > 1:
                raise InputError(f"На листе «{table.sheet}» несколько колонок кода ТН ВЭД.")
            code_col = code_cols[0] + 1 if code_cols else len(table.headers) + 1
            comments_col = table.col("Комментарий")
            comments_col = comments_col + 1 if comments_col is not None else None
            formula_comments = comments_col is not None and any(
                sheet == table.sheet and ci == comments_col - 1 for sheet, ri, ci in formula_cells
            )
            if formula_comments:
                comments_col = None
            sheet_edits = edits.setdefault(table.sheet, {})
            sheet_added = added.setdefault(table.sheet, {})
            if not code_cols:
                sheet_edits[f"{get_column_letter(code_col)}{table.header_row}"] = ("Код ТНВЭД", False)
                sheet_added[code_col] = 16
            for ri, row in table.rows:
                name = table.get(row, "Наименование", "Номенклатура")
                if name is None or norm(name) in ("итого", "всего", "общий итог"):
                    continue
                existing = row[code_col - 1].value if code_cols else None
                existing = formula_cells.get((table.sheet, ri, code_col - 1), existing)
                data = {h: row[i].value for i, h in enumerate(table.headers) if h}
                features = extract_features(data)
                article = str(table.get(row, "Артикул", "Код") or "")
                item = {
                    "id": f"{table.sheet}:{ri}",
                    "sheet": table.sheet,
                    "row": ri,
                    "article": article,
                    "name": str(name),
                    "original_code": existing,
                    "signature": features.signature,
                    "features": asdict(features),
                }
                if existing not in (None, "") and not options.get("verify_existing", False):
                    item.update(
                        code=existing,
                        status="Уже имел код",
                        comment="Исходный код сохранён без проверки.",
                        evidence=None,
                        candidates=[],
                    )
                else:
                    result = engine.classify(features)
                    item.update(result)
                    if result["code"] and (not valid_code(result["code"]) or not result["evidence"]):
                        raise IntegrityError("Нельзя записать непроверенный код ТН ВЭД.")
                    sheet_edits[f"{get_column_letter(code_col)}{ri}"] = (result["code"] or "", True)
                    if not result["code"]:
                        if not comments_col:
                            comments_col = max(len(table.headers), code_col) + 1
                            sheet_edits[f"{get_column_letter(comments_col)}{table.header_row}"] = (
                                "Комментарий ТН ВЭД" if formula_comments else "Комментарий",
                                False,
                            )
                            sheet_added[comments_col] = 44
                        old = row[comments_col - 1].value if comments_col <= len(row) else None
                        comment = str(old or "")
                        if result["comment"] not in comment:
                            comment = (comment + "\n" + result["comment"]).strip()
                        sheet_edits[f"{get_column_letter(comments_col)}{ri}"] = (comment, False)
                items.append(item)
                progress(
                    min(90, 5 + int(len(items) / max(total, 1) * 85)), f"Обработано товаров: {len(items)}"
                )
    finally:
        client.close()
    if not items:
        raise InputError("В Excel не найдены товарные строки с наименованием.")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_name = Path(file.original_name).stem + "_с_кодами_ТНВЭД.xlsx"
    path = output_dir / output_name
    progress(95, "Проверка сохранности Excel")
    patch_workbook(file.path, path, edits, added)
    counts = {
        s: sum(i["status"] == s for i in items)
        for s in ("Уже имел код", "Код определён", "Требуется уточнение", "Техническая ошибка")
    }
    return (
        {"title": file.original_name, "total": len(items), "counts": counts},
        {"items": items},
        path,
        output_name,
        [],
    )


def re_code_header(value):
    return norm(value).replace(" ", "") == "кодтнвэд"
