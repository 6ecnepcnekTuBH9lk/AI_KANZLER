"""Development inspection against captured Alta cards, never used by the application."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.modules.tnved.alta import CandidateFinder
from app.modules.tnved.classifier import ClassificationEngine
from app.modules.tnved.features import extract_features

FIXTURES = ROOT / "backend/tests/fixtures/tnved"


class SnapshotClient:
    def __init__(self):
        self.data = json.loads((FIXTURES / "alta.json").read_text(encoding="utf-8"))

    def verify(self, code):
        return self.data["cards"][code]

    def close(self):
        pass


def engine():
    client = SnapshotClient()
    result = ClassificationEngine(client)
    routing = CandidateFinder(client)
    result.finder.find = lambda f: sorted(
        {c for h in routing.headings(f) for c in client.data["headings"][h]}
    )
    return result


def main():
    baseline = json.loads((FIXTURES / "baseline.json").read_text(encoding="utf-8"))
    classifier = engine()
    rows = []
    for rownum, row in enumerate(baseline["rows"], 2):
        features = extract_features(row)
        result = classifier.classify(features)
        rows.append({"row": rownum, "source": row, "result": result})
        facts = [x for x in result["missing_input"] if not x.startswith("исключение альтернативы:")]
        print(
            rownum,
            features.kind,
            features.material,
            result["code"],
            result["reason_categories"],
            "; ".join(facts[:5]),
            "; ".join(result["missing_rule"][:2]),
            flush=True,
        )
    out = ROOT / "test-results/real-tnved/inspection.json"
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
