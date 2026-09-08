"""Explicit fixture maintenance, never called automatically by pytest.

Capture only cells of the three selected tables, with cached values and formats.
No photographs, macros, links or unrelated FACT collections are retained.
Golden output is a change detector; independent arithmetic tests are also required.
"""

import argparse
import hashlib
import json
import sys
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.modules.merchandise import importers
from app.modules.merchandise.presentation import UNIT_KEYS, display_units
from app.modules.merchandise.service import run
from openpyxl import Workbook

DIRECTORY = ROOT / "backend/tests/fixtures/merchandise"
NAMES = [
    "ОЗ26_W33_план_сезона 28.08+фото.xlsx",
    "План сезона ОЗ 26-27 из ценообразования.xlsx",
    "Анализ продаж (Общий) (XLSX) 2026-09-06.xlsx",
]
KEYS = (
    "article",
    "base",
    "target",
    "season_plan",
    "plan_pct",
    "plan_units",
    "preseason",
    "season_fact",
    "st",
    "execution",
    "gap_pp",
    "gap_units",
    "pace",
    "required",
    "cover",
    "forecast",
    "forecast_st",
    "status",
    "primary_cause",
    "secondary_cause",
    "recommendation",
    "second_wave",
    "season_observation_start",
    "season_observation_days",
    "preliminary_band",
    "operational_state",
    "operational_signal",
    "earliest_status_review_date",
    "preseason_estimated",
    "preseason_partial",
)


def materialize(directory):
    data = json.loads((DIRECTORY / "inputs.json").read_text(encoding="utf-8"))
    directory.mkdir(parents=True, exist_ok=True)
    files = []
    for table in data["tables"]:
        wb = Workbook()
        ws = wb.active
        ws.title = table["sheet"]
        for ri, cells in table["rows"]:
            for ci, value, fmt in cells:
                if isinstance(value, dict):
                    value = datetime.fromisoformat(value["date"])
                cell = ws.cell(ri, ci, value)
                cell.number_format = fmt
        path = directory / table["file"]
        wb.save(path)
        files.append(SimpleNamespace(path=path, original_name=table["file"]))
    return files


def snapshot(rows):
    return [
        {
            **{key: row.get(key) for key in KEYS},
            "display_units": {key: display_units(row[key]) for key in sorted(UNIT_KEYS) if key in row},
        }
        for row in rows
    ]


def capture():
    inputs = Path.home() / "Downloads"
    files = [SimpleNamespace(path=inputs / n, original_name=n) for n in NAMES]
    roles = importers.detect_roles(files)
    tables = []
    for role, (file, table) in roles.items():
        rows = list(enumerate(table.preamble, 1)) + [
            (ri, row)
            for ri, row in table.rows
            if role == "category" or str(table.get(row, "Артикул") or "").startswith("6A")
        ]
        cells = [
            [
                ri,
                [
                    [
                        ci,
                        {"date": c.value.isoformat()} if isinstance(c.value, (date, datetime)) else c.value,
                        c.fmt,
                    ]
                    for ci, c in enumerate(row, 1)
                    if c.value is not None
                ],
            ]
            for ri, row in rows
        ]
        tables.append(
            {
                "file": file.original_name,
                "source_sha256": hashlib.sha256(file.path.read_bytes()).hexdigest(),
                "sheet": table.sheet,
                "header_row": table.header_row,
                "rows": cells,
            }
        )
    DIRECTORY.mkdir(parents=True, exist_ok=True)
    (DIRECTORY / "inputs.json").write_text(
        json.dumps(
            {
                "description": "Реальные исходные значения 06.09.2026, без фотографий и сторонних коллекций. Сохраняются номера строк и форматы ячеек.",
                "tables": tables,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--capture-inputs", action="store_true")
    parser.add_argument("--accept-results", action="store_true")
    args = parser.parse_args()
    if args.capture_inputs:
        capture()
    if args.accept_results:
        files = materialize(ROOT / "test-results/golden-inputs")
        result, sections, *_ = run(files, {}, ROOT / "test-results/golden-output", lambda *_: None)
        # One article per line keeps reviews practical.
        rows = snapshot(sections["articles"])
        (DIRECTORY / "expected.json").write_text(
            "[\n" + ",\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n]\n",
            encoding="utf-8",
        )
        print(json.dumps({"articles": len(rows), "counts": result["counts"]}, ensure_ascii=False))
