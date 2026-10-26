"""Build the public KR/TW timeline using only official sources (Python stdlib)."""
from __future__ import annotations

import argparse
import copy
import hashlib
import html
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import time
from datetime import date, datetime, timezone
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen
from timeline_localization import Localizer

ROOT = Path(__file__).resolve().parents[1]
CATEGORIES = {"story": "劇情大項目", "major": "改版大項目", "minor": "小項目", "collaboration": "合作"}
KR = "https://mabinogi.nexon.com"
TW = "https://mabinogi.beanfun.com"
SINCE = "2025-01-01"


def clean(value):
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


class Element:
    def __init__(self, tag="root", attrs=(), parent=None):
        self.tag, self.attrs, self.parent, self.children = tag, dict(attrs), parent, []

    def text(self):
        if self.tag in ("script", "style"):
            return ""
        return clean(" ".join(c.text() if isinstance(c, Element) else c for c in self.children))

    def walk(self):
        yield self
        for child in self.children:
            if isinstance(child, Element):
                yield from child.walk()


class Document(HTMLParser):
    VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}

    def __init__(self, value):
        super().__init__(convert_charrefs=True)
        self.root = self.current = Element()
        self.feed(value)

    def handle_starttag(self, tag, attrs):
        item = Element(tag, attrs, self.current)
        self.current.children.append(item)
        if tag not in self.VOID:
            self.current = item

    def handle_startendtag(self, tag, attrs):
        self.current.children.append(Element(tag, attrs, self.current))

    def handle_endtag(self, tag):
        item = self.current
        while item.parent:
            if item.tag == tag:
                self.current = item.parent
                return
            item = item.parent

    def handle_data(self, data):
        self.current.children.append(data)


def iso(value):
    match = re.search(r"(20\d{2})[./-](\d{1,2})[./-](\d{1,2})", str(value))
    if not match:
        return None
    try:
        return date(*map(int, match.groups())).isoformat()
    except ValueError:
        return None


def official(url, region):
    parsed = urlparse(url)
    hosts = {"kr": {"mabinogi.nexon.com", "kr-newsroom.nexon.com"},
             "tw": {"mabinogi.beanfun.com", "mabinogi-event.beanfun.com", "tw-event.beanfun.com", "mabinogi-gama-event.beanfun.com"}}
    return parsed.scheme == "https" and parsed.hostname in hosts[region] and not parsed.username


def kr_rows(value):
    result = {}
    for anchor in Document(value).root.walk():
        href = html.unescape(anchor.attrs.get("href", ""))
        if anchor.tag != "a" or not re.search(r"(?:notice|update)_view\.asp\?.*\bid=\d+", href):
            continue
        url, title = urljoin(KR + "/page/news/", href), anchor.text()
        if not official(url, "kr") or not title:
            continue
        parent, published = anchor, None
        # Dates belong to the enclosing list row, never the whole list/page.
        for _ in range(5):
            published = iso(parent.text())
            if published or parent.parent is None:
                break
            parent = parent.parent
            if parent.tag in ("ul", "tbody", "body", "html"):
                break
        if published:
            result[url] = {"url": url, "title": title, "publishedDate": published}
    return list(result.values())


def release_date(title, body, published):
    if re.search(r"테스트|\[개발중\]|사전|쇼케이스", title, re.I):
        return None
    if "[적용됨]" in title:
        return published
    # Patch notices are normally posted two days before the actual patch.
    match = re.search(r"(20\d{2})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일.{0,20}패치", body)
    if match:
        return iso("-".join(match.groups()))
    match = re.search(r"(\d{1,2})/(\d{1,2})\([^)]*\)\s*정식\s*서버.*변경점", title)
    if match:
        year = int(published[:4])
        if int(match[1]) == 1 and published[5:7] == "12":
            year += 1
        return iso(f"{year}-{match[1]}-{match[2]}")
    if re.search(r"마비노기\s*[x×]|업데이트 안내", title, re.I):
        # Event notices must state the start date; publication is insufficient.
        match = re.search(r"(20\d{2})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일.{0,35}(?:부터|~|～)", body)
        if match:
            return iso("-".join(match.groups()))
    return None


def classify(title):
    if re.search(r"마비노기\s*[x×]", title, re.I):
        return "collaboration", None
    story = re.search(r"\b(G\d{2})\b", title, re.I)
    if story:
        return "story", story[1].lower()
    for name, group in ((r"RE\s*:\s*ACTION", "reaction"), (r"NEW\s+RISE", "new-rise"), (r"NEW\s+LIFE", "new-life")):
        if re.search(name, title, re.I):
            return "major", group
    return "minor", None


def relevant(title):
    if re.search(r"테스트|\[개발중\]|사전|쇼케이스|쿠폰|현상|종료|예정", title):
        return False
    return bool(re.search(r"정식\s*서버.*변경점|\[적용됨\]|마비노기\s*[x×]|업데이트 안내", title, re.I))


class Client:
    def __init__(self, cache_dir):
        self.directory = Path(cache_dir)
        self.directory.mkdir(parents=True, exist_ok=True)

    def get(self, url, payload=None, ttl=21600):
        data = json.dumps(payload).encode() if payload is not None else None
        key = hashlib.sha256(url.encode() + (data or b"")).hexdigest()
        path = self.directory / (key + ".json")
        if path.exists():
            cached = json.loads(path.read_text(encoding="utf-8"))
            if time.time() - cached["savedAt"] < ttl:
                return cached["body"]
        for attempt in range(3):
            try:
                request = Request(url, data=data, headers={"User-Agent": "MabinogiActivityTimeline/1.0 (+https://github.com/jet23058/mabinogi-activity)", "Content-Type": "application/json", "Accept": "text/html,application/json"})
                with urlopen(request, timeout=25) as response:
                    raw = response.read()
                    charset = response.headers.get_content_charset()
                    if not charset:
                        meta = re.search(br"charset\s*=\s*[\"']?([\w-]+)", raw[:8000], re.I)
                        charset = meta[1].decode() if meta else "utf-8"
                    body = raw.decode(charset, errors="strict")
                path.write_text(json.dumps({"savedAt": time.time(), "body": body}, ensure_ascii=False), encoding="utf-8")
                time.sleep(0.15)
                return body
            except Exception:
                if attempt == 2:
                    raise
                time.sleep(attempt + 1)


def crawl_kr(client, archive, today):
    rows = {r["url"]: r for r in archive}
    for kind, max_pages in (("notice", 120), ("update", 8)):
        seen = set()
        for page in range(1, max_pages + 1):
            value = client.get(f"{KR}/page/news/{kind}_list.asp?page={page}", ttl=21600 if page <= 3 else 604800)
            batch = kr_rows(value)
            if not batch:
                raise ValueError(f"KR {kind} index parser returned no rows, page {page}")
            fresh = [r for r in batch if r["url"] not in seen]
            seen.update(r["url"] for r in batch)
            if not fresh:
                break  # Detect repeated pages / pinned rows instead of looping.
            for row in fresh:
                if SINCE <= row["publishedDate"] <= today and relevant(row["title"]):
                    rows[row["url"]] = row
            if max(r["publishedDate"] for r in fresh) < SINCE:
                break
        else:
            raise ValueError(f"KR {kind} pagination limit reached before {SINCE}")
    print(f"KR index: {len(rows)} relevant notices", flush=True)
    for row in rows.values():
        # Revisit recent details so corrections by the publisher can be detected.
        if not row.get("checkedDate") or row["publishedDate"] >= today[:7] + "-01":
            raw = client.get(row["url"])
            body = Document(raw).root.text()
            start = body.find(row["title"])
            if start >= 0:
                body = body[start:]
            body = body.split("주소복사")[0]
            row["text"] = body
            row["releaseDate"] = release_date(row["title"], body, row["publishedDate"])
            row["checkedDate"] = today
    return sorted(rows.values(), key=lambda r: (r["publishedDate"], r["url"]))


def crawl_tw(client, archive, today):
    rows = {r["url"]: r for r in archive}
    seen = set()
    for page in range(1, 101):
        payload = {"kind": 0, "page": page, "pageSize": 100, "method": 3, "bid": 0, "toAll": 0, "searchText": "", "alt": 0}
        result = json.loads(client.get(f"{TW}/api/Bullentin/PostBullentinList", payload, ttl=21600 if page <= 2 else 604800))
        data = result.get("data", {})
        batch = data.get("bulletins")
        if result.get("code") != 1 or not isinstance(batch, list) or not batch:
            raise ValueError(f"TW index unavailable, page {page}")
        fresh = [r for r in batch if str(r.get("bullentinId")) not in seen]
        seen.update(str(r.get("bullentinId")) for r in batch)
        if not fresh:
            break
        for item in fresh:
            published, title = iso(item.get("startDate")), clean(item.get("title", ""))
            bid = str(item.get("bullentinId", ""))
            if not bid.isdigit() or not published or not SINCE <= published <= today:
                continue
            if not re.search(r"改善|更新|改版|開機|合作|聯動|G\d{2}|NEW\s*(?:RISE|LIFE)|RE:ACTION|祕法|秘法|名匠|深淵", title, re.I):
                continue
            url = f"{TW}/News?catId=inside&bid={bid}"
            if url not in rows or published >= today[:7] + "-01":
                detail = json.loads(client.get(f"{TW}/api/Bullentin/GetBullentin?Bid={bid}"))
                row = detail.get("data", {}).get("myDataSet", {}).get("table", {})
                if isinstance(row, list):
                    row = row[0] if row else {}
                # Some index entries redirect to campaigns and have no API body.
                # Keep index evidence and any earlier successfully fetched body.
                available = detail.get("code") == 1 and isinstance(row, dict) and str(row.get("bullentinId")) == bid and isinstance(row.get("content"), str)
                if not available and url in rows:
                    continue
                doc = Document(row["content"] if available else "")
                links = sorted({urljoin(TW + "/", a.attrs["href"]) for a in doc.root.walk() if a.tag == "a" and a.attrs.get("href") and official(urljoin(TW + "/", a.attrs["href"]), "tw")})
                rows[url] = {"url": url, "title": title, "publishedDate": published, "text": doc.root.text(), "links": links, "detailStatus": "available" if available else "unavailable"}
                if not available:
                    print(f"TW {bid}: campaign entry without readable API body; kept as index-only candidate", flush=True)
        dates = [iso(r.get("startDate")) for r in fresh]
        if (dates and all(d and d < SINCE for d in dates)) or page >= int(data.get("totalPage", page + 1)):
            break
    else:
        raise ValueError("TW pagination limit reached")
    print(f"TW index: {len(rows)} relevant notices", flush=True)
    return sorted(rows.values(), key=lambda r: (r["publishedDate"], r["url"]))


def validate_event(event):
    assert event.get("id") and event.get("title"), "Missing id/title"
    assert event["category"] in CATEGORIES, "Unknown category"
    for region in ("kr", "tw"):
        info = event[region]
        assert info["status"] in ("released", "announced", "pending"), "Unknown release status"
        if info["status"] != "pending":
            assert iso(info.get("date")) == info.get("date") and info.get("date"), "Missing/invalid release date"
            assert info.get("sources"), "A release date requires official evidence"
        else:
            assert info.get("date") is None, "Pending dates must be null"
        for source in info.get("sources", []):
            assert official(source["url"], region), "Non-official source"


def routine_patch_notice(title):
    return bool(re.search(r"정식\s*서버.*(?:패치|업데이트).*변경점\s*안내|正式伺服器更新內容公告", title))


def build(catalog, kr, tw, today):
    events = copy.deepcopy(catalog["events"])
    covered = {s["url"] for e in events for s in e["kr"]["sources"]}
    review = []
    for row in kr:
        # Raw patch notices remain in source-index as evidence. They are never
        # promoted to visible events: a feature needs a meaningful curated title.
        if row["url"] in covered or routine_patch_notice(row["title"]):
            continue
        review.append({"region": "kr", "reason": "待整理為具體功能項目，不直接顯示於時間軸。", **row})
    ids = set()
    for event in events:
        validate_event(event)
        assert not routine_patch_notice(event["title"]), "Use a concrete feature title instead of a patch headline"
        assert event["id"] not in ids, "Duplicate event id"
        ids.add(event["id"])
        event["curated"] = True
        event["categoryLabel"] = CATEGORIES[event["category"]]
        event["importance"] = "major" if event["category"] in ("story", "major") else "normal"
        event["tw"]["label"] = {"pending": "實裝日期待確認", "released": "已實裝", "announced": "已公告"}[event["tw"]["status"]]
        if event["tw"].get("matchStatus") == "partial":
            event["tw"]["label"] = "部分對應（個別項目待核對）"
        terms = catalog.get("twSearchTerms", {}).get(event["id"], [])
        matches = [r for r in tw if terms and any(t.casefold() in (r["title"] + " " + r["text"]).casefold() for t in terms)]
        # Search matches are suggestions, never automatically treated as releases.
        event["tw"]["candidateSources"] = [{"url": r["url"], "title": r["title"], "publishedDate": r["publishedDate"]} for r in matches]
    events.sort(key=lambda e: (e["kr"]["date"] or "9999", e["id"]))
    groups = []
    for group_id in sorted({e.get("groupId") for e in events if e.get("groupId")}):
        children = [e for e in events if e.get("groupId") == group_id]
        groups.append({"id": group_id, "title": catalog.get("groupTitles", {}).get(group_id, group_id.upper()),
                       "category": children[0]["category"], "krStartDate": children[0]["kr"]["date"],
                       "krEndDate": children[-1]["kr"]["date"], "eventIds": [e["id"] for e in children]})
    groups.sort(key=lambda g: (g["krStartDate"] or "9999", g["id"]))
    return {"schemaVersion": 1, "asOf": today, "locale": "zh-TW", "sortBy": "kr.date",
            "coverage": {"from": SINCE, "to": today, "complete": False, "note": "已核對項目與官網自動收錄；非所有更新的完整清單。待確認不代表台版尚未實裝。"},
            "selectionPolicy": copy.deepcopy(catalog.get("selectionPolicy", {"mode": "curated-features"})),
            "categories": [{"id": key, "label": value} for key, value in CATEGORIES.items()],
            "groups": groups, "events": events, "reviewQueue": review}


def read(path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    if not path.exists() or path.read_text(encoding="utf-8") != content:
        temp = path.with_suffix(".tmp")
        temp.write_text(content, encoding="utf-8")
        temp.replace(path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--research", action="store_true", help="Extract features from bodies and cross-match TW evidence with AI")
    parser.add_argument("--offline", action="store_true", help="Build from saved source archive without network")
    parser.add_argument("--cache-dir", default=str(ROOT / ".cache/timeline"))
    parser.add_argument("--today", default=datetime.now(timezone.utc).astimezone(__import__("zoneinfo").ZoneInfo("Asia/Taipei")).date().isoformat())
    args = parser.parse_args()
    ai = None
    if args.research and not args.offline:
        from research_timeline import AI
        ai = AI(args.cache_dir)
    catalog = read(ROOT / "timeline/curated.json", {})
    archive = read(ROOT / "timeline/source-index.json", {"kr": [], "tw": []})
    if not args.offline:
        client = Client(args.cache_dir)
        # Do not publish or overwrite the last good data on a crawl/parser failure.
        archive = {"kr": crawl_kr(client, archive["kr"], args.today), "tw": crawl_tw(client, archive["tw"], args.today)}
    findings = []
    if ai:
        from research_timeline import research
        catalog, findings, state = research(catalog, archive, client, ai, read(ROOT / "timeline/research-state.json", {}), args.today)
        write(ROOT / "timeline/research-state.json", state)
    result = build(catalog, archive["kr"], archive["tw"], args.today)
    result["reviewQueue"].extend(findings)
    assert result["events"], "Refusing to publish an empty timeline"
    localizer = Localizer(read(ROOT / "timeline/localization.json", {}),
                          read(ROOT / "timeline/translations.json", {}), offline=args.offline)
    result = localizer.apply(result)
    write(ROOT / "timeline/translations.json", localizer.cache)
    write(ROOT / "timeline/source-index.json", archive)
    write(ROOT / "update-timeline.json", result)
    print(f"Built {len(result['events'])} events / {len(result['groups'])} groups, {len(result['reviewQueue'])} announcements awaiting feature review")


if __name__ == "__main__":
    main()
