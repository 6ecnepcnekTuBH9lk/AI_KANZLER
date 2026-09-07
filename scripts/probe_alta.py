from pathlib import Path

import httpx
from bs4 import BeautifulSoup

for code in ("6110-search", "6110-tree"):
    url = (
        "https://www.alta.ru/tnved/search/?tnstr=6110"
        if code == "6110-search"
        else "https://www.alta.ru/tnved/get_tree/?tnved=6110"
    )
    r = httpx.get(url, timeout=25, follow_redirects=True)
    print(code, r.status_code)
    Path(f"docs/source-review/alta-{code}.html").write_text(r.text, encoding="utf-8")
    print(r.text[:6000])
    soup = BeautifulSoup(r.text, "lxml")
    for el in soup.select("form, .jTnvedTree"):
        print(str(el)[:16000])
