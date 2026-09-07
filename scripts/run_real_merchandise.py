"""Local acceptance run. Reads inputs; outputs only inside this project."""

import json
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.modules.merchandise.service import run

inputs = Path("C:/Users/Ermolenko.i/Downloads")
names = [
    "ОЗ26_W33_план_сезона 28.08+фото.xlsx",
    "План сезона ОЗ 26-27 из ценообразования.xlsx",
    "Анализ продаж (Общий) (XLSX) 2026-09-06.xlsx",
]
files = [SimpleNamespace(path=inputs / n, original_name=n) for n in names]
result, sections, path, name, weekly = run(
    files, {}, ROOT / "test-results/real-merchandise", lambda p, m: print(p, m, flush=True)
)
(ROOT / "test-results/real-merchandise/result.json").write_text(
    json.dumps({"result": result, "sections": sections}, ensure_ascii=False, indent=2), encoding="utf-8"
)
print(json.dumps(result["display_summary"], ensure_ascii=False, indent=2))
print(path)
