import hashlib
import re
import threading
import time
from datetime import UTC, datetime
from urllib.parse import urljoin, urlparse

import httpx
from app.core.exceptions import SourceUnavailable
from bs4 import BeautifulSoup


class AltaClient:
    """Open Alta endpoints, no auth/captcha bypass. Cache scoped to one analysis."""

    _lock = threading.Lock()
    _last = 0.0

    def __init__(self, transport=None, interval=0.6):
        self.http = httpx.Client(
            timeout=20,
            transport=transport,
            follow_redirects=False,
            headers={"User-Agent": "KANZLER-Business-Platform/0.1 (internal classification)"},
        )
        self.interval, self.cache = interval, {}

    def close(self):
        self.http.close()

    def get(self, path, params=None):
        key = path + str(params)
        if key in self.cache:
            return self.cache[key]
        url = urljoin("https://www.alta.ru", path)
        if urlparse(url).hostname != "www.alta.ru":
            raise SourceUnavailable("Источник кода должен находиться на Alta.ru.")
        for attempt in range(3):
            with self._lock:
                delay = self.interval - (time.monotonic() - type(self)._last)
                if delay > 0:
                    time.sleep(delay)
                type(self)._last = time.monotonic()
            try:
                response = self.http.get(url, params=params)
                if response.status_code in (401, 403, 429):
                    raise SourceUnavailable("Не удалось проверить код на Alta.ru: доступ ограничен сайтом.")
                if response.status_code == 404:
                    self.cache[key] = ""
                    return ""
                response.raise_for_status()
                self.cache[key] = response.text
                return response.text
            except httpx.HTTPError as exc:
                if attempt == 2:
                    raise SourceUnavailable(
                        "Не удалось проверить код на Alta.ru: сайт или раздел недоступен."
                    ) from exc
                time.sleep(0.5 * 2**attempt)
        raise SourceUnavailable("Не удалось проверить код на Alta.ru.")

    def verify(self, code):
        html = self.get(f"/tnved/code/{code}/")
        soup = BeautifulSoup(html, "lxml")
        marker = soup.select_one(f'[data-original-code="{code}"]')
        tree = soup.select_one("ul.pTnved_position")
        if marker is None or tree is None:
            raise SourceUnavailable(
                "Не удалось проверить код на Alta.ru: код отсутствует или структура страницы изменилась."
            )
        levels = []
        for li in tree.select("li.pTnved_item"):
            divs = li.find_all("div", recursive=False)
            if len(divs) >= 2:
                levels.append(
                    {
                        "code": divs[0].get_text(" ", strip=True),
                        "description": divs[1].get_text(" ", strip=True),
                    }
                )
        if not levels or re.sub(r"\D", "", levels[-1]["code"]) != code:
            raise SourceUnavailable("Не удалось проверить полный код в дереве Alta.ru.")
        return {
            "code": code,
            "url": f"https://www.alta.ru/tnved/code/{code}/",
            "levels": levels,
            "description": " → ".join(x["description"] for x in levels),
            "verified_at": datetime.now(UTC).isoformat(),
            "sha256": hashlib.sha256(html.encode()).hexdigest(),
        }


class CandidateFinder:
    # Search routing only, never final codes. Every leaf is discovered and verified at Alta.
    def __init__(self, client):
        self.client = client

    def headings(self, f):
        male = f.gender == "мужской"
        if f.kind == "обувь":
            return ["6401", "6402", "6403", "6404", "6405"]
        if f.knit:
            return {
                "футболка": ["6109"],
                "рубашка": ["6105" if male else "6106"],
                "джемпер": ["6110"],
                "брюки": ["6103" if male else "6104"],
                "шорты": ["6103" if male else "6104"],
                "пиджак": ["6103" if male else "6104"],
                "куртка": ["6101" if male else "6102"],
                "пальто": ["6101" if male else "6102"],
                "носки": ["6115"],
                "галстук": ["6117"],
                "шарф": ["6117"],
            }.get(f.kind, [])
        return {
            "рубашка": ["6205" if male else "6206"],
            "джинсы": ["6203" if male else "6204"],
            "брюки": ["6203" if male else "6204"],
            "шорты": ["6203" if male else "6204"],
            "пиджак": ["6203" if male else "6204"],
            "куртка": ["6201" if male else "6202"],
            "пальто": ["6201" if male else "6202"],
            "галстук": ["6215"],
            "шарф": ["6214"],
            "ремень": ["4203"],
        }.get(f.kind, [])

    def find(self, features):
        headings = self.headings(features)
        if not headings:
            return []
        codes = set()
        for heading in headings:
            html = self.client.get("/tnved/get_tree/", {"tnved": heading})
            soup = BeautifulSoup(html, "lxml")
            nodes = soup.select("li[data-source]")
            roots = [n for n in nodes if n.get("data-source") in (heading, heading + "0")]
            if not roots and heading.endswith("0"):
                # Alta stores some headings without their final zero (6110 -> 611).
                html = self.client.get("/tnved/get_tree/", {"tnved": heading.rstrip("0")})
                nodes = BeautifulSoup(html, "lxml").select("li[data-source]")
                roots = [
                    n for n in nodes if n.get("data-source") in (heading, heading + "0", heading.rstrip("0"))
                ]
            if not roots:
                raise SourceUnavailable(
                    "Не удалось проверить код на Alta.ru: изменилось дерево товарных позиций."
                )
            queue = list(roots)
            seen = set()
            while queue:
                node = queue.pop()
                source, uin = node.get("data-source", ""), node.get("data-uin")
                if uin in seen:
                    continue
                seen.add(uin)
                anchor = node.select_one('a[href*="/tnved/code/"]')
                if anchor:
                    m = re.search(r"/code/(\d{10})", anchor.get("href", ""))
                    if m and m[1].startswith(heading):
                        codes.add(m[1])
                children = node.find_all("li", recursive=True)
                if children:
                    queue.extend(children)
                elif "jstree-closed" in node.get("class", []) and uin:
                    child_html = self.client.get("/tnved/get_tree/", {"uin": uin})
                    queue.extend(BeautifulSoup(child_html, "lxml").select("li[data-source]"))
                elif re.fullmatch(r"\d{10}", source) and source.startswith(heading):
                    codes.add(source)
                if len(seen) > 500:
                    raise SourceUnavailable(
                        "Дерево Alta.ru слишком велико для однозначной автоматической проверки этой позиции."
                    )
        return sorted(codes)
