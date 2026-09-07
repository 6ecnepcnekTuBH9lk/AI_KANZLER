"""Read-only checks of real results and bundled source integrity."""

import hashlib
import json
from pathlib import Path
from zipfile import ZipFile

from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[1]
resources = ROOT / "backend/app/resources"
manifest = {}
for package in ("kanzler-merchandise-performance-controller", "tnved-code-filler"):
    with ZipFile(Path.home() / "Downloads" / f"{package}.zip") as archive:
        for member in archive.infolist():
            if member.is_dir() or member.filename.startswith("__MACOSX/"):
                continue
            relative = member.filename.removeprefix(package + "/")
            target = resources / package / relative
            assert target.is_file(), target
            original = archive.read(member)
            assert target.read_bytes() == original, target
            manifest[target.relative_to(resources).as_posix()] = hashlib.sha256(original).hexdigest()
(ROOT / "docs/RESOURCE_MANIFEST.json").write_text(
    json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
)

merch = json.loads((ROOT / "test-results/real-merchandise/result.json").read_text(encoding="utf-8"))
merch_file = next((ROOT / "test-results/real-merchandise").glob("*.xlsx"))
wb = load_workbook(merch_file, data_only=True)
assert len(wb.sheetnames) == 8
assert wb["Артикулы"].max_row - 1 == len(merch["sections"]["articles"]) == 338
summary = dict(wb["Сводка"].iter_rows(min_row=2, values_only=True))
for key, value in merch["result"]["display_summary"].items():
    exported = summary[key]
    assert (abs(exported - value) < 1e-7) if isinstance(value, (int, float)) else exported == value
for ws in wb:
    assert ws.freeze_panes and ws.auto_filter.ref
    assert all(dim.width <= 45 for dim in ws.column_dimensions.values())
    assert all(dim.height <= 42 for dim in ws.row_dimensions.values() if dim.height)
wb.close()

tnved = json.loads((ROOT / "test-results/real-tnved/result.json").read_text(encoding="utf-8"))
tnved_file = next((ROOT / "test-results/real-tnved").glob("*.xlsx"))
wb = load_workbook(tnved_file)
assert tnved["result"]["total"] == 57
for item in tnved["sections"]["items"]:
    if item["status"] == "Код определён":
        code = item["code"]
        assert isinstance(code, str) and len(code) == 10 and code.isascii() and code.isdigit()
        assert item["evidence"]["url"] == f"https://www.alta.ru/tnved/code/{code}/"
    elif item["status"] != "Уже имел код":
        assert item["code"] is None and item["comment"]
wb.close()
report = {
    "resource_files_unchanged": len(manifest),
    "merchandise": merch["result"]["display_summary"],
    "tnved": tnved["result"],
    "verified_outputs": [str(merch_file), str(tnved_file)],
}
(ROOT / "test-results/verification.json").write_text(
    json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
)
print(json.dumps(report, ensure_ascii=False, indent=2))
