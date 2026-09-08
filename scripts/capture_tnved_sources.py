"""Capture public Alta evidence for offline regression; not a production code table."""

import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.modules.tnved.alta import AltaClient, CandidateFinder

DEST = ROOT / "backend/tests/fixtures/tnved"


def main():
    client = AltaClient()
    finder = CandidateFinder(client)
    target = DEST / "alta.json"
    captured = (
        json.loads(target.read_text(encoding="utf-8"))
        if target.exists()
        else {"headings": {}, "cards": {}, "notes": {}}
    )
    try:
        for heading in (
            "6109",
            "6103",
            "6203",
            "6110",
            "6201",
            "6215",
            "6401",
            "6402",
            "6403",
            "6404",
            "6405",
            "6105",
            "6205",
            "6115",
            "6214",
            "4203",
            "6117",
        ):
            if heading in captured["headings"]:
                continue
            finder.headings = lambda f, h=heading: [h]
            codes = finder.find(SimpleNamespace())
            for code in codes:
                if code not in captured["cards"]:
                    captured["cards"][code] = client.verify(code)
            captured["headings"][heading] = codes
            target.write_text(json.dumps(captured, ensure_ascii=False, indent=2), encoding="utf-8")
            print(heading, len(codes), "verified", flush=True)
        for key in (
            "R11",
            "G61",
            "G62",
            "G64",
            "P6109",
            "P6110",
            "P6203",
            "P6401",
            "P6402",
            "P6403",
            "P6404",
            "P6405",
        ):
            href = f"/poyasnenia/{key}/"
            html = client.get(href)
            soup = BeautifulSoup(html, "lxml")
            for unwanted in soup.select("script, style, header, footer, nav"):
                unwanted.decompose()
            captured["notes"][key] = {
                "url": "https://www.alta.ru" + href,
                "text": soup.get_text(" ", strip=True),
                "sha256": hashlib.sha256(html.encode()).hexdigest(),
                "verified_at": datetime.now(UTC).isoformat(),
            }
        target.write_text(json.dumps(captured, ensure_ascii=False, indent=2), encoding="utf-8")
    finally:
        client.close()


if __name__ == "__main__":
    main()
