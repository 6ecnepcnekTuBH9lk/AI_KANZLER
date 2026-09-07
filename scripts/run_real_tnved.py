"""Live Alta acceptance run, source workbook remains untouched."""

import json
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.modules.tnved.service import run

path = Path("C:/Users/Ermolenko.i/Downloads/Артикулы_коллеции_ВЛ_27_Нет_кодов_ТНВЭД_2.xlsx")
output = ROOT / "test-results/real-tnved"
result, sections, file, name, _ = run(
    [SimpleNamespace(path=path, original_name=path.name)],
    {},
    output,
    lambda p, m: print(p, m, flush=True),
    None,
)
(output / "result.json").write_text(
    json.dumps({"result": result, "sections": sections}, ensure_ascii=False, indent=2), encoding="utf-8"
)
print(result)
print(file)
