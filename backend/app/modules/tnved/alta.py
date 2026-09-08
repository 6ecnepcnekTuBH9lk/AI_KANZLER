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
        if (
            urlparse(url).hostname != "www.alta.ru"
            or urlparse(url).scheme != "https"
            or urlparse(url).port not in (None, 443)
        ):
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
        if not isinstance(code, str) or not re.fullmatch(r"[0-9]{10}", code):
            raise SourceUnavailable("Нельзя проверить неполный или некорректный код Alta.")
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
        if (
            len(levels) < 4
            or re.sub(r"\D", "", levels[-1]["code"]) != code
            or re.sub(r"\D", "", levels[1]["code"]) != code[:2]
            or re.sub(r"\D", "", levels[2]["code"]) != code[:4]
            or any(not level["description"] for level in levels)
        ):
            raise SourceUnavailable("Не удалось проверить полный код в дереве Alta.ru.")
        return {
            "code": code,
            "url": f"https://www.alta.ru/tnved/code/{code}/",
            "levels": levels,
            "description": " → ".join(x["description"] for x in levels),
            "verified_at": datetime.now(UTC).isoformat(),
            "sha256": hashlib.sha256(html.encode()).hexdigest(),
        }

    def explanations(self, features, cards):
        keys = (
            ["G64"]
            if features.kind == "обувь"
            else ["R11"]
            if cards[0]["code"].startswith(("61", "62"))
            else []
        )
        if features.kind == "джемпер":
            keys.append("P6110")
        result = []
        anchors = {
            "R11": ("преобладает по массе", "примечания к субпозициям"),
            "G64": ("подошв", "верх"),
            "P6110": ("джемпер", "поло"),
        }
        for key in keys:
            path = f"/poyasnenia/{key}/"
            html = self.get(path)
            text = BeautifulSoup(html, "lxml").get_text(" ", strip=True).lower().replace("ё", "е")
            if not all(anchor in text for anchor in anchors[key]):
                raise SourceUnavailable("Не удалось проверить актуальные пояснения Alta: " + key)
            result.append(
                {
                    "url": "https://www.alta.ru" + path,
                    "sha256": hashlib.sha256(html.encode()).hexdigest(),
                    "verified_at": datetime.now(UTC).isoformat(),
                    "rule": key,
                }
            )
        return result

    def discover_tik(self, features):
        """Public TIK search is discovery only; never return a verified classification."""
        query = " ".join(
            str(value)
            for value in (
                features.kind or features.details.get("описание товара", ""),
                features.gender,
                "трикотаж" if features.knit is True else "нетрикотажный" if features.knit is False else None,
                features.main_text,
            )
            if value
        )[:500]
        html = self.get("/tik/", {"srchstr": query})
        soup = BeautifulSoup(html, "lxml")
        codes = set()
        for anchor in soup.select('a[href*="/tnved/code/"]'):
            match = re.search(r"/tnved/code/([0-9]{10})/", anchor.get("href", ""))
            if match:
                codes.add(match[1])
        return sorted(codes), {
            "source": "https://www.alta.ru/tik/",
            "query": query,
            "purpose": "DISCOVERY_ONLY",
            "sha256": hashlib.sha256(html.encode()).hexdigest(),
        }


class CandidateFinder:
    # Search routing only, never final codes. Every leaf is discovered and verified at Alta.
    def __init__(self, client):
        self.client = client
        self.discovery = []

    def headings(self, f):
        male = f.gender == "мужской"
        if f.kind == "обувь":
            return ["6401", "6402", "6403", "6404", "6405"]
        if f.knit is None and f.kind != "ремень":
            return []
        if f.gender is None and f.kind in (
            "рубашка",
            "пиджак",
            "брюки",
            "джинсы",
            "шорты",
            "куртка",
            "пальто",
        ):
            from dataclasses import replace

            return sorted(
                set(self.headings(replace(f, gender="мужской")) + self.headings(replace(f, gender="женский")))
            )
        if f.knit:
            return {
                "футболка": ["6109"],
                "рубашка": ["6105" if male else "6106"],
                "джемпер": ["6110"],
                "брюки": ["6103" if male else "6104"],
                "джинсы": ["6103" if male else "6104"],
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
        self.discovery = []
        if not headings and hasattr(self.client, "discover_tik"):
            candidates, trace = self.client.discover_tik(features)
            self.discovery.append(trace)
            headings = sorted({code[:4] for code in candidates})
            if len(headings) > 10:
                raise SourceUnavailable(
                    "Поиск Alta дал слишком много товарных позиций; уточните вид изделия."
                )
        if not headings:
            return []
        self.discovery.append(
            {
                "source": "https://www.alta.ru/tnved/",
                "headings": headings,
                "purpose": "EXHAUSTIVE_TREE_DISCOVERY",
            }
        )
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
                identity = (uin, source)
                if identity in seen:
                    continue
                seen.add(identity)
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
                    child_nodes = BeautifulSoup(child_html, "lxml").select("li[data-source]")
                    if not child_nodes:
                        raise SourceUnavailable("Не удалось загрузить все дочерние ветви дерева Alta.")
                    queue.extend(child_nodes)
                elif re.fullmatch(r"\d{10}", source) and source.startswith(heading):
                    codes.add(source)
                elif not anchor:
                    raise SourceUnavailable("В дереве Alta обнаружена незавершённая ветвь.")
                if len(seen) > 500:
                    raise SourceUnavailable(
                        "Дерево Alta.ru слишком велико для однозначной автоматической проверки этой позиции."
                    )
        return sorted(codes)
